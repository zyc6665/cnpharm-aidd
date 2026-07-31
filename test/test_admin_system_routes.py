"""管理员系统路由测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.dependencies import get_current_user
from app.auth.password import hash_password
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import tools as _tool_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
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
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "expected_keys"),
    [
        ("/api/v1/system/info", {"app_name", "app_version", "environment"}),
        ("/api/v1/system/stats", {"total_users", "total_tools", "total_tasks"}),
        ("/api/v1/system/config", {"environment", "database", "storage"}),
        ("/api/v1/system/feature-flags", {"environment", "items", "total"}),
    ],
)
async def test_admin_system_routes_use_standard_response_shape(
    api_client: httpx.AsyncClient,
    path: str,
    expected_keys: set[str],
):
    """管理员系统接口应返回统一响应结构。"""
    response = await api_client.get(
        path,
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert expected_keys.issubset(payload["data"].keys())


@pytest.mark.asyncio
async def test_feature_flags_endpoint_exposes_aidd_release_gates(
    api_client: httpx.AsyncClient,
):
    """管理员应能审计首月 AIDD 发布门禁开关。"""
    response = await api_client.get(
        "/api/v1/system/feature-flags",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    items = {item["key"]: item for item in payload["items"]}
    expected_keys = {
        "AIDD_PROJECT_WORKSPACE_ENABLED",
        "AIDD_PROJECT_CONVERSATIONS_ENABLED",
        "TOOL_PACKAGE_V1_ENABLED",
        "PROJECT_RESEARCH_BOARD_ENABLED",
        "LEGACY_AIDD_API_ENABLED",
    }

    assert set(items) == expected_keys
    assert payload["total"] == len(expected_keys)
    assert all(isinstance(item["enabled"], bool) for item in items.values())
    assert all(
        item["source"] in {"default", "configured", "environment"}
        for item in items.values()
    )
    assert all("rollout" in item for item in items.values())
    assert all(
        item["rollout"]["scope"] in {"all", "allowlist", "closed"}
        for item in items.values()
    )
    assert all(isinstance(item["rollout"]["user_count"], int) for item in items.values())
    assert items["PROJECT_RESEARCH_BOARD_ENABLED"]["description"]
