"""管理员用户路由测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.dependencies import get_current_user
from app.auth.password import hash_password, verify_password
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import tools as _tool_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.files import File, FileAccessLog
from app.models.statistics import FileStatistics, ToolStatistics, UserStatistics
from app.models.tasks import Task, TaskInput, TaskLog, TaskOutput, TaskStatus
from app.models.tools import Tool, ToolFavorite, ToolVersion
from app.models.users import AuthSource, User, UserRole, UserStatus


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """创建隔离数据库会话。"""
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
async def admin_user(db_session: AsyncSession) -> User:
    """创建管理员用户。"""
    user = User(
        email="admin@example.com",
        password_hash=hash_password("AdminSecret123"),
        display_name="Admin",
        role=UserRole.ADMIN.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def normal_user(db_session: AsyncSession) -> User:
    """创建普通用户。"""
    user = User(
        email="member@example.com",
        password_hash=hash_password("MemberSecret123"),
        display_name="Member User",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, admin_user: User):
    """创建带依赖覆盖的 API 客户端。"""

    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        if authorization == "Bearer admin-token":
            return admin_user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_stats_route_is_not_shadowed_by_user_detail_route(
    api_client: httpx.AsyncClient,
):
    """管理员统计路由不应被用户详情动态路由覆盖。"""
    response = await api_client.get(
        "/api/v1/users/admin/stats",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["total_users"] == 1
    assert payload["data"]["admin_users"] == 1


@pytest.mark.asyncio
async def test_admin_user_list_route_uses_standard_response_shape(
    api_client: httpx.AsyncClient,
):
    """管理员用户列表应返回统一响应结构。"""
    response = await api_client.get(
        "/api/v1/users/admin",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["total"] == 1
    assert len(payload["data"]["items"]) == 1
    assert payload["data"]["items"][0]["email"] == "admin@example.com"


@pytest.mark.asyncio
async def test_admin_user_list_route_supports_display_name_keyword_search(
    api_client: httpx.AsyncClient,
    normal_user: User,
):
    """管理员用户列表应支持按显示名搜索。"""
    response = await api_client.get(
        "/api/v1/users/admin",
        params={"keyword": "Member"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["total"] == 1
    assert payload["data"]["items"][0]["email"] == "member@example.com"


@pytest.mark.asyncio
async def test_admin_user_list_route_normalizes_legacy_disabled_status(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """管理员用户列表应将旧状态值归一化为 disabled。"""
    legacy_user = User(
        email="legacy@example.com",
        password_hash="hashed-password",
        display_name="Legacy User",
        role=UserRole.USER.value,
        status="banned",
    )
    db_session.add(legacy_user)
    await db_session.commit()

    response = await api_client.get(
        "/api/v1/users/admin",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    legacy_item = next(item for item in payload["data"]["items"] if item["email"] == "legacy@example.com")
    assert legacy_item["status"] == UserStatus.DISABLED.value


@pytest.mark.asyncio
async def test_admin_update_user_accepts_disabled_status(
    api_client: httpx.AsyncClient,
    normal_user: User,
):
    """管理员更新用户状态时应接受 disabled。"""
    response = await api_client.patch(
        f"/api/v1/users/admin/{normal_user.id}",
        json={"status": UserStatus.DISABLED.value},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["message"] == "用户更新成功"
    assert payload["data"]["status"] == UserStatus.DISABLED.value


@pytest.mark.asyncio
async def test_admin_delete_user_sets_disabled_status(
    api_client: httpx.AsyncClient,
    normal_user: User,
    db_session: AsyncSession,
):
    """管理员删除用户应统一落为 disabled 状态。"""
    response = await api_client.delete(
        f"/api/v1/users/admin/{normal_user.id}",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["message"] == "用户已删除"

    await db_session.refresh(normal_user)
    assert normal_user.status == UserStatus.DISABLED.value


@pytest.mark.asyncio
async def test_admin_create_user_creates_hashed_password(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """管理员应能直接创建新用户。"""
    response = await api_client.post(
        "/api/v1/users/admin",
        json={
            "username": "created",
            "email": "created@example.com",
            "display_name": "Created User",
            "password": "CreatedSecret123",
            "role": UserRole.USER.value,
            "status": UserStatus.PENDING.value,
        },
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["code"] == 201
    assert payload["message"] == "用户创建成功"
    assert payload["data"]["email"] == "created@example.com"
    assert payload["data"]["role"] == UserRole.USER.value
    assert payload["data"]["status"] == UserStatus.PENDING.value

    result = await db_session.execute(select(User).where(User.email == "created@example.com"))
    created_user = result.scalar_one()
    assert verify_password("CreatedSecret123", created_user.password_hash) is True


@pytest.mark.asyncio
async def test_admin_reset_user_password_updates_hash(
    api_client: httpx.AsyncClient,
    normal_user: User,
    db_session: AsyncSession,
):
    """管理员应能直接重置目标用户密码。"""
    response = await api_client.post(
        f"/api/v1/users/admin/{normal_user.id}/reset-password",
        json={"new_password": "ResetSecret123"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["message"] == "密码重置成功"

    await db_session.refresh(normal_user)
    assert verify_password("ResetSecret123", normal_user.password_hash) is True


@pytest.mark.asyncio
async def test_admin_hard_delete_user_cascades_related_records(
    api_client: httpx.AsyncClient,
    admin_user: User,
    normal_user: User,
    db_session: AsyncSession,
):
    """管理员真删除用户时应级联清理其关联数据。"""
    user_statistics = UserStatistics(user_id=normal_user.id, total_tasks=3)

    reviewed_tool = Tool(
        owner_id=admin_user.id,
        reviewed_by=normal_user.id,
        name="Reviewed Tool",
        slug="reviewed-tool",
    )
    owned_tool = Tool(
        owner_id=normal_user.id,
        name="Owned Tool",
        slug="owned-tool",
    )
    owned_file = File(
        owner_id=normal_user.id,
        filename="owned.txt",
        size_bytes=10,
        sha256="a" * 64,
        storage_path="/tmp/owned.txt",
    )
    other_file = File(
        owner_id=admin_user.id,
        filename="other.txt",
        size_bytes=10,
        sha256="b" * 64,
        storage_path="/tmp/other.txt",
    )

    db_session.add_all([user_statistics, reviewed_tool, owned_tool, owned_file, other_file])
    await db_session.flush()

    owned_version = ToolVersion(
        tool_id=owned_tool.id,
        version="v1.0.0",
        config={"type": "python_script"},
    )
    db_session.add(owned_version)
    await db_session.flush()

    task = Task(
        user_id=normal_user.id,
        tool_id=owned_tool.id,
        tool_version_id=owned_version.id,
        status=TaskStatus.PENDING.value,
    )
    db_session.add(task)
    await db_session.flush()

    db_session.add_all([
        ToolStatistics(tool_id=owned_tool.id, usage_count=1),
        FileStatistics(file_id=owned_file.id, download_count=1),
        FileAccessLog(file_id=owned_file.id, user_id=normal_user.id, action="upload"),
        FileAccessLog(file_id=other_file.id, user_id=normal_user.id, action="download"),
        TaskInput(task_id=task.id, params={"foo": "bar"}, file_ids=[owned_file.id]),
        TaskOutput(task_id=task.id, result={"ok": True}, file_ids=[owned_file.id]),
        TaskLog(task_id=task.id, message="created"),
        ToolFavorite(user_id=normal_user.id, tool_id=reviewed_tool.id),
    ])
    await db_session.commit()

    response = await api_client.delete(
        f"/api/v1/users/admin/{normal_user.id}",
        params={"hard": "true"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["message"] == "用户已彻底删除"

    assert await db_session.get(User, normal_user.id) is None
    assert await db_session.get(UserStatistics, normal_user.id) is None
    assert await db_session.get(Tool, owned_tool.id) is None
    assert await db_session.get(ToolVersion, owned_version.id) is None
    assert await db_session.get(ToolStatistics, owned_tool.id) is None
    assert await db_session.get(Task, task.id) is None

    task_input_result = await db_session.execute(select(TaskInput).where(TaskInput.task_id == task.id))
    assert task_input_result.scalar_one_or_none() is None

    task_output_result = await db_session.execute(select(TaskOutput).where(TaskOutput.task_id == task.id))
    assert task_output_result.scalar_one_or_none() is None

    task_log_result = await db_session.execute(select(TaskLog).where(TaskLog.task_id == task.id))
    assert task_log_result.scalar_one_or_none() is None

    assert await db_session.get(File, owned_file.id) is None
    assert await db_session.get(FileStatistics, owned_file.id) is None

    owned_file_log_result = await db_session.execute(
        select(FileAccessLog).where(FileAccessLog.user_id == normal_user.id)
    )
    assert owned_file_log_result.scalar_one_or_none() is None

    favorite_result = await db_session.execute(
        select(ToolFavorite).where(ToolFavorite.user_id == normal_user.id)
    )
    assert favorite_result.scalar_one_or_none() is None

    await db_session.refresh(reviewed_tool)
    assert reviewed_tool.reviewed_by is None


@pytest.mark.asyncio
async def test_admin_create_sso_user_without_password(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """SSO_AUTO_PROVISION=false 的部署可以预建 sso 账号：无平台口令、sso_uid 留空。"""
    response = await api_client.post(
        "/api/v1/users/admin",
        json={
            "username": "preseeded-sso",
            "email": "preseeded@example.com",
            "display_name": "Preseeded SSO",
            "auth_source": "sso",
            "role": UserRole.USER.value,
            "status": UserStatus.ACTIVE.value,
        },
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 201
    assert response.json()["message"] == "用户创建成功"

    result = await db_session.execute(
        select(User).where(User.username == "preseeded-sso")
    )
    created_user = result.scalar_one()
    assert created_user.auth_source == AuthSource.SSO.value
    # sso 账号的口令由统一身份认证托管，平台侧必须为空
    assert created_user.password_hash is None
    # 留空表示首次统一认证登录时按用户名匹配后回填
    assert created_user.sso_uid is None


@pytest.mark.asyncio
async def test_admin_create_sso_user_ignores_supplied_password(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """即使请求里带了口令，sso 账号也不能把口令落库。"""
    response = await api_client.post(
        "/api/v1/users/admin",
        json={
            "username": "preseeded-sso-pwd",
            "email": "preseeded-pwd@example.com",
            "auth_source": "sso",
            "password": "SsoIgnored123",
            "role": UserRole.USER.value,
            "status": UserStatus.ACTIVE.value,
        },
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 201
    result = await db_session.execute(
        select(User).where(User.username == "preseeded-sso-pwd")
    )
    created_user = result.scalar_one()
    assert created_user.password_hash is None


@pytest.mark.asyncio
async def test_admin_create_local_user_still_requires_password(
    api_client: httpx.AsyncClient,
):
    """local 分支不能被放宽：缺口令仍是 40002。"""
    response = await api_client.post(
        "/api/v1/users/admin",
        json={
            "username": "local-no-pwd",
            "email": "local-no-pwd@example.com",
            "auth_source": "local",
            "role": UserRole.USER.value,
            "status": UserStatus.ACTIVE.value,
        },
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 40002


@pytest.mark.asyncio
async def test_admin_create_user_rejects_unknown_auth_source(
    api_client: httpx.AsyncClient,
):
    """认证源是枚举，未知值必须在 schema 层被拒。"""
    response = await api_client.post(
        "/api/v1/users/admin",
        json={
            "username": "unknown-source",
            "auth_source": "iam",
            "password": "UnknownSource123",
            "role": UserRole.USER.value,
            "status": UserStatus.ACTIVE.value,
        },
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# D-06：sso_uid 绑定/解绑（统一身份标识的唯一写入口）
# --------------------------------------------------------------------------- #
class _FakeAdminAudit:
    """只收管理操作：这些用例关心的是「sso_uid 变更进审计」这件事本身。"""

    def __init__(self):
        self.operations = []

    def log_admin_operation(self, **kwargs):
        self.operations.append(kwargs)

    def log_admin_delete(self, **kwargs):
        self.operations.append(kwargs)


@pytest.fixture
def admin_audit(monkeypatch):
    from app.api.v1 import users as admin_module

    fake = _FakeAdminAudit()
    monkeypatch.setattr(admin_module, "get_audit_logger", lambda: fake)
    return fake


async def _make_sso_user(
    db: AsyncSession,
    *,
    email: str,
    auth_source: str = AuthSource.SSO.value,
    sso_uid: str | None = None,
) -> User:
    """直接落库预置账号：走 HTTP 建号的话 sso 账号还得先有认证源，绕一圈没意义。"""
    user = User(
        email=email,
        display_name=email.split("@", 1)[0],
        auth_source=auth_source,
        sso_uid=sso_uid,
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_admin_bind_sso_uid_on_sso_account(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_audit,
):
    """sso 账号可以绑定统一身份标识，并把 before/after 落进同一条审计。"""
    from app.logging.audit import AuditAction

    user = await _make_sso_user(db_session, email="bind@example.com")

    response = await api_client.patch(
        f"/api/v1/users/admin/{user.id}",
        json={"sso_uid": "iam-1"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    await db_session.refresh(user)
    assert user.sso_uid == "iam-1"
    audit = admin_audit.operations[-1]
    assert audit["changes"]["sso_uid"] == {"before": None, "after": "iam-1"}
    assert audit["reason"] == "sso_uid_bind"
    assert audit["action"] == AuditAction.ADMIN_USER_UPDATE


@pytest.mark.asyncio
async def test_admin_unbind_sso_uid_with_blank(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_audit,
):
    """空串/纯空白 = 解绑，且必须落 NULL —— 落 '' 会撞部分唯一索引。"""
    user = await _make_sso_user(db_session, email="unbind@example.com", sso_uid="iam-1")

    response = await api_client.patch(
        f"/api/v1/users/admin/{user.id}",
        json={"sso_uid": "   "},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    await db_session.refresh(user)
    assert user.sso_uid is None
    audit = admin_audit.operations[-1]
    assert audit["reason"] == "sso_uid_unbind"
    # 解绑也要留 before/after：只记 reason 的话，事后查不出解掉的是哪个 uid。
    assert audit["changes"]["sso_uid"] == {"before": "iam-1", "after": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_source", [AuthSource.LOCAL.value, AuthSource.LDAP.value])
async def test_admin_rejects_sso_uid_on_non_sso_account(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_audit,
    auth_source: str,
):
    """非 sso 账号（local / ldap）不得挂 sso_uid：否则同时具备口令与 SSO 两条入口。"""
    user = await _make_sso_user(
        db_session,
        email=f"{auth_source}-bind@example.com",
        auth_source=auth_source,
    )

    response = await api_client.patch(
        f"/api/v1/users/admin/{user.id}",
        json={"sso_uid": "iam-2"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == 40002
    assert "认证源" in payload["message"]
    await db_session.refresh(user)
    assert user.sso_uid is None


@pytest.mark.asyncio
async def test_admin_noop_blank_sso_uid_on_local_account(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_audit,
):
    """解绑 no-op 不该被认证源拦：local 账号本来就没有 sso_uid。"""
    user = await _make_sso_user(
        db_session, email="local-noop@example.com", auth_source=AuthSource.LOCAL.value
    )

    response = await api_client.patch(
        f"/api/v1/users/admin/{user.id}",
        json={"sso_uid": ""},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    assert "reason" not in admin_audit.operations[-1]


@pytest.mark.asyncio
async def test_admin_duplicate_sso_uid_returns_40002(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_audit,
):
    """一个 sso_uid 只能绑一个账号：预检冲突用 400+40002（不是 409）。"""
    await _make_sso_user(db_session, email="owner@example.com", sso_uid="iam-a")
    user = await _make_sso_user(db_session, email="dup@example.com", sso_uid="iam-b")

    response = await api_client.patch(
        f"/api/v1/users/admin/{user.id}",
        json={"sso_uid": "iam-a"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == 40002
    assert "已绑定其他账号" in payload["message"]
    await db_session.refresh(user)
    assert user.sso_uid == "iam-b"


@pytest.mark.asyncio
async def test_admin_sso_uid_max_length(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """列宽是 String(128)：超长必须在 schema 层 422，不能等到落库报错。"""
    user = await _make_sso_user(db_session, email="toolong@example.com")

    response = await api_client.patch(
        f"/api/v1/users/admin/{user.id}",
        json={"sso_uid": "x" * 129},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 422

    # 上限是 128，不是 127：边界两侧都要钉，别把合法 uid 判死。
    at_limit = await api_client.patch(
        f"/api/v1/users/admin/{user.id}",
        json={"sso_uid": "y" * 128},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert at_limit.status_code == 200
    await db_session.refresh(user)
    assert user.sso_uid == "y" * 128


@pytest.mark.asyncio
async def test_admin_patch_without_sso_uid_keeps_binding(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_audit,
):
    """没传 sso_uid 就不该动它，也不该在审计里冒出 sso_uid 键。"""
    user = await _make_sso_user(db_session, email="keep@example.com", sso_uid="iam-1")

    response = await api_client.patch(
        f"/api/v1/users/admin/{user.id}",
        json={"status": UserStatus.DISABLED.value},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    await db_session.refresh(user)
    assert user.sso_uid == "iam-1"
    assert "sso_uid" not in admin_audit.operations[-1]["changes"]


@pytest.mark.asyncio
async def test_admin_sso_uid_integrity_error_maps_to_40002(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_audit,
    monkeypatch,
):
    """预检与写入之间有并发窗口：flush 撞唯一索引也要转成 400+40002，而不是 500。"""
    from app.api.v1 import users as admin_module

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(admin_module, "ensure_sso_uid_unique", _noop)
    await _make_sso_user(db_session, email="taken@example.com", sso_uid="taken")
    user = await _make_sso_user(db_session, email="race@example.com")

    response = await api_client.patch(
        f"/api/v1/users/admin/{user.id}",
        json={"sso_uid": "taken"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 40002


# --------------------------------------------------------------------------- #
# D-07：建号用户名口径与 SSO 认人口径同宽（64）
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_admin_create_username_64_accepted_65_rejected(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """建号侧边界：64 字符能建、65 字符被 schema 拒绝。

    登录侧见 ``test_sso_governance.py::test_64_char_preseeded_username_can_login``。
    两侧必须同宽：建得进却登不进（旧 ``_USERNAME_MAX_LENGTH=56``）等于白建。
    """
    username_64 = "u" * 64
    created = await api_client.post(
        "/api/v1/users/admin",
        json={
            "username": username_64,
            "email": "boundary-64@example.com",
            "auth_source": "sso",
            "role": UserRole.USER.value,
            "status": UserStatus.ACTIVE.value,
        },
        headers={"Authorization": "Bearer admin-token"},
    )

    assert created.status_code == 201
    result = await db_session.execute(select(User).where(User.username == username_64))
    assert result.scalar_one().username == username_64

    username_65 = "v" * 65
    rejected = await api_client.post(
        "/api/v1/users/admin",
        json={
            "username": username_65,
            "email": "boundary-65@example.com",
            "auth_source": "sso",
            "role": UserRole.USER.value,
            "status": UserStatus.ACTIVE.value,
        },
        headers={"Authorization": "Bearer admin-token"},
    )

    assert rejected.status_code == 422
    result = await db_session.execute(select(User).where(User.username == username_65))
    assert result.scalar_one_or_none() is None
