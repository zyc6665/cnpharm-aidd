"""Short-lived signed file URL tests for remote-tool inputs."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import Header
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user_optional
from app.database.base import Base
from app.database.session import get_db
from app.files.remote_access_tokens import (
    RemoteFileAccessTokenError,
    create_remote_file_access_token,
    validate_remote_file_access_token,
)
from app.main import app
from app.models import statistics as _statistics_models  # noqa: F401
from app.models.files import File as FileModel, FileSourceType
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
async def test_private_file_download_accepts_valid_remote_token(
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
