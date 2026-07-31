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
from app.models.users import User, UserRole, UserStatus


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
