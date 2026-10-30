"""Short-lived signed file URL tests for remote-tool inputs."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import Header
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.database.base import Base
from app.database.session import get_db
from app.files.remote_access_tokens import (
    RemoteFileAccessTokenError,
    create_browser_file_access_token,
    create_remote_file_access_token,
    validate_browser_file_access_token,
    validate_remote_file_access_token,
)
from app.main import app
from app.models import statistics as _statistics_models  # noqa: F401
from app.models.files import File as FileModel, FileSourceType
from app.models.projects import Organization, Project, ProjectMember
from app.models.users import User, UserRole, UserStatus


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    user = User(
        email="owner@example.com",
        password_hash="hashed-password",
        display_name="Owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_remote_file_access_token_allows_only_bound_file_and_task():
    token = create_remote_file_access_token(
        file_id="file-a",
        task_id="task-a",
        expires_in_seconds=300,
    )

    claims = validate_remote_file_access_token(token, file_id="file-a", task_id="task-a")

    assert claims["file_id"] == "file-a"
    assert claims["task_id"] == "task-a"
    with pytest.raises(RemoteFileAccessTokenError):
        validate_remote_file_access_token(token, file_id="file-b", task_id="task-a")
    with pytest.raises(RemoteFileAccessTokenError):
        validate_remote_file_access_token(token, file_id="file-a", task_id="task-b")


@pytest.mark.asyncio
async def test_remote_file_access_token_rejects_expired_tokens():
    token = create_remote_file_access_token(
        file_id="file-a",
        task_id="task-a",
        expires_in_seconds=-1,
    )

    with pytest.raises(RemoteFileAccessTokenError):
        validate_remote_file_access_token(token, file_id="file-a", task_id="task-a")


@pytest.mark.asyncio
async def test_browser_file_access_token_is_scoped_to_file_and_expires():
    token = create_browser_file_access_token(
        file_id="file-a",
        user_id="user-a",
        expires_in_seconds=300,
    )

    claims = validate_browser_file_access_token(token, file_id="file-a", user_id="user-a")

    assert claims["file_id"] == "file-a"
    assert claims["user_id"] == "user-a"
    with pytest.raises(RemoteFileAccessTokenError):
        validate_browser_file_access_token(token, file_id="file-b", user_id="user-a")


@pytest.mark.asyncio
async def test_download_url_returns_short_lived_browser_url(
    db_session: AsyncSession,
    owner: User,
    tmp_path,
):
    file_path = tmp_path / "molecules.sdf"
    file_path.write_text("$$$$\n", encoding="utf-8")
    file_record = FileModel(
        owner_id=owner.id,
        filename="molecules.sdf",
        content_type="chemical/x-mdl-sdfile",
        size_bytes=file_path.stat().st_size,
        sha256="0" * 64,
        storage_path=str(file_path),
        source_type=FileSourceType.UPLOAD.value,
        is_public=False,
    )
    db_session.add(file_record)
    await db_session.commit()
    await db_session.refresh(file_record)

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return owner

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                f"/api/v1/files/{file_record.id}/download-url",
                params={"expires_in": 300},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    download_url = response.json()["data"]["url"]
    assert download_url.startswith(f"/api/v1/files/{file_record.id}/download?token=")
    token = download_url.split("token=", 1)[1]
    claims = validate_browser_file_access_token(token, file_id=file_record.id, user_id=owner.id)
    assert claims["user_id"] == owner.id


@pytest.mark.asyncio
async def test_private_file_download_accepts_valid_remote_token(
    db_session: AsyncSession,
    owner: User,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.api.v1 import files as files_api
    from app.logging.audit import AuditAction, AuditResult

    file_path = tmp_path / "protein.pdb"
    # 用 write_bytes 避免 Windows 文本模式把 \n 转成 \r\n，保证下载内容逐字节可比。
    file_path.write_bytes(b"ATOM\nEND\n")
    file_record = FileModel(
        owner_id=owner.id,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=file_path.stat().st_size,
        sha256="0" * 64,
        storage_path=str(file_path),
        source_type=FileSourceType.UPLOAD.value,
        is_public=False,
    )
    db_session.add(file_record)
    await db_session.commit()
    await db_session.refresh(file_record)

    token = create_remote_file_access_token(
        file_id=file_record.id,
        task_id="task-a",
        expires_in_seconds=300,
    )
    audit_events: list[dict[str, object]] = []

    class AuditRecorder:
        def log_file_operation(self, **kwargs):
            audit_events.append(kwargs)

    async def override_get_db():
        yield db_session

    async def override_get_current_user_optional(
        authorization: str | None = Header(default=None),
    ):
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
    monkeypatch.setattr(
        files_api,
        "get_audit_logger",
        lambda: AuditRecorder(),
    )
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                f"/api/v1/files/{file_record.id}/download",
                params={"token": token},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.text == "ATOM\nEND\n"
    assert audit_events == [
        {
            "user_id": "remote-token",
            "action": AuditAction.FILE_DOWNLOAD,
            "file_id": file_record.id,
            "file_name": "protein.pdb",
            "result": AuditResult.SUCCESS,
            "file_size": file_path.stat().st_size,
            "project_id": None,
            "remote_token": True,
        }
    ]


@pytest.mark.asyncio
async def test_authenticated_file_download_records_audit_event(
    db_session: AsyncSession,
    owner: User,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.api.v1 import files as files_api
    from app.logging.audit import AuditAction, AuditResult

    file_path = tmp_path / "protein.pdb"
    file_path.write_text("ATOM\nEND\n", encoding="utf-8")
    file_record = FileModel(
        owner_id=owner.id,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=file_path.stat().st_size,
        sha256="0" * 64,
        storage_path=str(file_path),
        source_type=FileSourceType.UPLOAD.value,
        is_public=False,
    )
    db_session.add(file_record)
    await db_session.commit()
    await db_session.refresh(file_record)
    audit_events: list[dict[str, object]] = []

    class AuditRecorder:
        def log_file_operation(self, **kwargs):
            audit_events.append(kwargs)

    async def override_get_db():
        yield db_session

    async def override_get_current_user_optional(
        authorization: str | None = Header(default=None),
    ):
        return owner if authorization == "Bearer owner-token" else None

    monkeypatch.setattr(
        files_api,
        "get_audit_logger",
        lambda: AuditRecorder(),
        raising=False,
    )
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                f"/api/v1/files/{file_record.id}/download",
                headers={"Authorization": "Bearer owner-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert audit_events == [
        {
            "user_id": owner.id,
            "action": AuditAction.FILE_DOWNLOAD,
            "file_id": file_record.id,
            "file_name": "protein.pdb",
            "result": AuditResult.SUCCESS,
            "file_size": file_path.stat().st_size,
            "project_id": None,
            "remote_token": False,
        }
    ]


@pytest.mark.asyncio
async def test_authenticated_file_download_denial_records_audit_event(
    db_session: AsyncSession,
    owner: User,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.api.v1 import files as files_api
    from app.logging.audit import AuditAction, AuditResult

    outsider = User(
        email="outsider@example.com",
        password_hash="hashed-password",
        display_name="Outsider",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(outsider)
    await db_session.flush()
    file_path = tmp_path / "private.pdb"
    file_path.write_text("ATOM\nEND\n", encoding="utf-8")
    file_record = FileModel(
        owner_id=owner.id,
        filename="private.pdb",
        content_type="chemical/x-pdb",
        size_bytes=file_path.stat().st_size,
        sha256="0" * 64,
        storage_path=str(file_path),
        source_type=FileSourceType.UPLOAD.value,
        is_public=False,
    )
    db_session.add(file_record)
    await db_session.commit()
    await db_session.refresh(file_record)
    audit_events: list[dict[str, object]] = []

    class AuditRecorder:
        def log_file_operation(self, **kwargs):
            audit_events.append(kwargs)

    async def override_get_db():
        yield db_session

    async def override_get_current_user_optional(
        authorization: str | None = Header(default=None),
    ):
        return outsider if authorization == "Bearer outsider-token" else None

    monkeypatch.setattr(
        files_api,
        "get_audit_logger",
        lambda: AuditRecorder(),
        raising=False,
    )
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                f"/api/v1/files/{file_record.id}/download",
                headers={"Authorization": "Bearer outsider-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert audit_events == [
        {
            "user_id": outsider.id,
            "action": AuditAction.FILE_DOWNLOAD,
            "file_id": file_record.id,
            "file_name": "private.pdb",
            "result": AuditResult.DENIED,
            "file_size": file_path.stat().st_size,
            "project_id": None,
            "remote_token": False,
            "reason": "forbidden",
        }
    ]


@pytest.mark.asyncio
async def test_project_file_download_uses_project_membership(
    db_session: AsyncSession,
    owner: User,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    """项目文件下载必须认项目成员，而不是只认 owner_id（C5）。

    owner 是文件所有者但已被移出项目（无 ProjectMember），应被拒绝；
    项目内 editor（非 owner）应被允许。
    """
    from app.logging.audit import AuditAction, AuditResult

    organization = Organization(name="Org", slug="org-c5")
    db_session.add(organization)
    await db_session.commit()
    await db_session.refresh(organization)

    project = Project(
        organization_id=organization.id,
        created_by=owner.id,
        name="Project C5",
    )
    member = User(
        email="member@example.com",
        password_hash="hashed-password",
        display_name="Member",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add_all([project, member])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(member)

    db_session.add(
        ProjectMember(project_id=project.id, user_id=member.id, role="editor")
    )
    await db_session.commit()

    file_path = tmp_path / "project-file.txt"
    file_path.write_text("hello", encoding="utf-8")
    file_record = FileModel(
        owner_id=owner.id,
        project_id=project.id,
        filename="project-file.txt",
        content_type="text/plain",
        size_bytes=file_path.stat().st_size,
        sha256="0" * 64,
        storage_path=str(file_path),
        source_type=FileSourceType.UPLOAD.value,
        is_public=False,
    )
    db_session.add(file_record)
    await db_session.commit()
    await db_session.refresh(file_record)

    audit_events: list[dict[str, object]] = []

    class AuditRecorder:
        def log_file_operation(self, **kwargs):
            audit_events.append(kwargs)

    async def override_get_db():
        yield db_session

    async def override_get_current_user_optional(
        authorization: str | None = Header(default=None),
    ):
        if authorization == "Bearer owner-token":
            return owner
        if authorization == "Bearer member-token":
            return member
        return None

    from app.api.v1 import files as files_api

    monkeypatch.setattr(
        files_api,
        "get_audit_logger",
        lambda: AuditRecorder(),
        raising=False,
    )
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            owner_response = await client.get(
                f"/api/v1/files/{file_record.id}/download",
                headers={"Authorization": "Bearer owner-token"},
            )
            member_response = await client.get(
                f"/api/v1/files/{file_record.id}/download",
                headers={"Authorization": "Bearer member-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert owner_response.status_code == 403
    assert member_response.status_code == 200
    assert member_response.text == "hello"
    assert audit_events[0]["reason"] == "forbidden"


def test_token_secret_requires_configured_secret(monkeypatch: pytest.MonkeyPatch):
    """密钥缺失时必须抛错，而不是回退到源码固定字符串（C6）。"""
    from app.config import settings

    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "")
    monkeypatch.setattr(settings, "SETTINGS_ENCRYPTION_KEY", None)

    with pytest.raises(RuntimeError, match="签名密钥未配置"):
        create_remote_file_access_token(file_id="file-a", task_id="task-a")


def test_browser_token_rejects_other_user():
    """浏览器下载令牌兑换时必须与当前请求者一致（C6）。"""
    token = create_browser_file_access_token(file_id="file-a", user_id="user-a")

    with pytest.raises(RemoteFileAccessTokenError, match="用户不匹配"):
        validate_browser_file_access_token(token, file_id="file-a", user_id="user-b")


# ---------------------------------------------------------------------------
# P1-2：被移出项目的 owner 不得再下载/删除项目文件（broken access control）
# ---------------------------------------------------------------------------


async def _create_user(
    db: AsyncSession, email: str, role: str = UserRole.USER.value
) -> User:
    user = User(
        email=email,
        password_hash="hashed-password",
        display_name=email,
        role=role,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _create_project(db: AsyncSession, creator: User, slug: str) -> Project:
    organization = Organization(name=slug, slug=slug)
    db.add(organization)
    await db.commit()
    await db.refresh(organization)
    project = Project(organization_id=organization.id, created_by=creator.id, name=slug)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


def _build_file(
    tmp_path,
    owner: User,
    filename: str,
    *,
    project_id: str | None = None,
    is_public: bool = False,
) -> FileModel:
    file_path = tmp_path / filename
    file_path.write_text("hello", encoding="utf-8")
    return FileModel(
        owner_id=owner.id,
        project_id=project_id,
        filename=filename,
        content_type="text/plain",
        size_bytes=file_path.stat().st_size,
        sha256="0" * 64,
        storage_path=str(file_path),
        source_type=FileSourceType.UPLOAD.value,
        is_public=is_public,
    )


@pytest.mark.asyncio
async def test_project_file_download_url_requires_project_membership(
    db_session: AsyncSession,
    owner: User,
    tmp_path,
):
    """download-url 对项目文件必须校验项目成员；被移出项目的 owner 被拒。"""
    member = await _create_user(db_session, "member-dl@example.com")
    admin = await _create_user(db_session, "admin-dl@example.com", role=UserRole.ADMIN.value)
    project = await _create_project(db_session, owner, "dl-url-project")
    db_session.add(ProjectMember(project_id=project.id, user_id=member.id, role="editor"))
    await db_session.commit()

    project_file = _build_file(tmp_path, owner, "project.txt", project_id=project.id)
    own_file = _build_file(tmp_path, owner, "own.txt")
    db_session.add_all([project_file, own_file])
    await db_session.commit()
    await db_session.refresh(project_file)
    await db_session.refresh(own_file)

    active_user = {"value": owner}

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return active_user["value"]

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        transport = httpx.ASGITransport(app=app)

        async def get_url(user: User, file_id: str) -> httpx.Response:
            active_user["value"] = user
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.get(
                    f"/api/v1/files/{file_id}/download-url",
                    params={"expires_in": 300},
                )

        owner_project_response = await get_url(owner, project_file.id)
        member_project_response = await get_url(member, project_file.id)
        admin_project_response = await get_url(admin, project_file.id)
        owner_own_response = await get_url(owner, own_file.id)
    finally:
        app.dependency_overrides.clear()

    assert owner_project_response.status_code == 403
    assert member_project_response.status_code == 200
    assert admin_project_response.status_code == 200
    assert owner_own_response.status_code == 200


@pytest.mark.asyncio
async def test_browser_download_token_rechecks_project_membership(
    db_session: AsyncSession,
    owner: User,
    tmp_path,
):
    """浏览器令牌只证明身份，兑换下载时仍须校验项目成员（不能跳过校验）。"""
    member = await _create_user(db_session, "member-token@example.com")
    project = await _create_project(db_session, owner, "token-project")
    db_session.add(ProjectMember(project_id=project.id, user_id=member.id, role="editor"))
    await db_session.commit()

    project_file = _build_file(tmp_path, owner, "token.txt", project_id=project.id)
    db_session.add(project_file)
    await db_session.commit()
    await db_session.refresh(project_file)

    owner_token = create_browser_file_access_token(
        file_id=project_file.id, user_id=owner.id
    )
    member_token = create_browser_file_access_token(
        file_id=project_file.id, user_id=member.id
    )

    async def override_get_db():
        yield db_session

    async def override_get_current_user_optional(
        authorization: str | None = Header(default=None),
    ):
        if authorization == "Bearer owner-token":
            return owner
        if authorization == "Bearer member-token":
            return member
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            owner_response = await client.get(
                f"/api/v1/files/{project_file.id}/download",
                params={"token": owner_token},
                headers={"Authorization": "Bearer owner-token"},
            )
            member_response = await client.get(
                f"/api/v1/files/{project_file.id}/download",
                params={"token": member_token},
                headers={"Authorization": "Bearer member-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert owner_response.status_code == 403
    assert member_response.status_code == 200
    assert member_response.text == "hello"


@pytest.mark.asyncio
async def test_project_file_delete_requires_project_membership(
    db_session: AsyncSession,
    owner: User,
    tmp_path,
):
    """删除/批量删除：项目成员或 admin 才可删；被移出的 owner 不可删。"""
    member = await _create_user(db_session, "member-del@example.com")
    admin = await _create_user(db_session, "admin-del@example.com", role=UserRole.ADMIN.value)
    project = await _create_project(db_session, owner, "del-project")
    db_session.add(ProjectMember(project_id=project.id, user_id=member.id, role="editor"))
    await db_session.commit()

    member_deletable = _build_file(tmp_path, owner, "del-member.txt", project_id=project.id)
    admin_deletable = _build_file(tmp_path, owner, "del-admin.txt", project_id=project.id)
    owner_rejected = _build_file(tmp_path, owner, "del-owner.txt", project_id=project.id)
    own_file = _build_file(tmp_path, owner, "del-own.txt")
    db_session.add_all([member_deletable, admin_deletable, owner_rejected, own_file])
    await db_session.commit()
    for record in (member_deletable, admin_deletable, owner_rejected, own_file):
        await db_session.refresh(record)

    active_user = {"value": owner}

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return active_user["value"]

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async def delete(user: User, file_id: str) -> httpx.Response:
                active_user["value"] = user
                return await client.delete(f"/api/v1/files/{file_id}")

            async def batch_delete(user: User, file_ids: list[str]) -> httpx.Response:
                active_user["value"] = user
                return await client.post("/api/v1/files/batch-delete", json=file_ids)

            owner_delete_response = await delete(owner, owner_rejected.id)
            member_delete_response = await delete(member, member_deletable.id)
            admin_delete_response = await delete(admin, admin_deletable.id)
            own_delete_response = await delete(owner, own_file.id)
            owner_batch_response = await batch_delete(owner, [owner_rejected.id])
            member_batch_response = await batch_delete(member, [owner_rejected.id])
    finally:
        app.dependency_overrides.clear()

    assert owner_delete_response.status_code == 403
    assert member_delete_response.status_code == 200
    assert admin_delete_response.status_code == 200
    assert own_delete_response.status_code == 200
    assert owner_batch_response.status_code == 200
    assert owner_batch_response.json()["data"]["deleted_count"] == 0
    assert owner_rejected.id in owner_batch_response.json()["data"]["failed_ids"]
    assert member_batch_response.status_code == 200
    assert member_batch_response.json()["data"]["deleted_count"] == 1

