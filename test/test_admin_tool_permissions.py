"""管理员工具写权限测试。"""

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

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.tools import Tool, ToolCategory, ToolStatus
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
        password_hash="hashed-password",
        display_name="Admin",
        role=UserRole.ADMIN.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> User:
    """创建普通用户。"""
    user = User(
        email="user@example.com",
        password_hash="hashed-password",
        display_name="User",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
    admin_user: User,
    regular_user: User,
):
    """创建带依赖覆盖的 API 客户端。"""

    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        if authorization == "Bearer admin-token":
            return admin_user
        if authorization == "Bearer user-token":
            return regular_user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    async def override_get_current_user_optional(
        authorization: str | None = Header(default=None),
    ) -> User | None:
        if authorization == "Bearer admin-token":
            return admin_user
        if authorization == "Bearer user-token":
            return regular_user
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_regular_user_cannot_write_tools(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    regular_user: User,
):
    """普通用户不能创建、更新、删除工具。"""
    category = ToolCategory(
        name="Docking",
        slug="docking",
        sort_order=0,
        is_enabled=True,
    )
    db_session.add(category)
    await db_session.flush()

    owned_tool = Tool(
        owner_id=regular_user.id,
        name="Owned Tool",
        slug="owned-tool",
        description="owned by regular user",
        category_id=category.id,
        category=category.name,
        status=ToolStatus.DRAFT.value,
        is_public=True,
    )
    db_session.add(owned_tool)
    await db_session.commit()

    create_response = await api_client.post(
        "/api/v1/tools",
        headers={"Authorization": "Bearer user-token"},
        json={
            "name": "User Created Tool",
            "slug": "user-created-tool",
            "category_id": category.id,
        },
    )
    assert create_response.status_code == 403

    update_response = await api_client.put(
        f"/api/v1/tools/{owned_tool.id}",
        headers={"Authorization": "Bearer user-token"},
        json={"name": "Should Fail"},
    )
    assert update_response.status_code == 403

    delete_response = await api_client.delete(
        f"/api/v1/tools/{owned_tool.id}",
        headers={"Authorization": "Bearer user-token"},
    )
    assert delete_response.status_code == 403


@pytest.mark.asyncio
async def test_admin_create_tool_requires_valid_enabled_category(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """管理员创建工具时必须提供有效且启用的分类。"""
    enabled_category = ToolCategory(
        name="Docking",
        slug="docking",
        sort_order=0,
        is_enabled=True,
    )
    disabled_category = ToolCategory(
        name="Disabled",
        slug="disabled",
        sort_order=1,
        is_enabled=False,
    )
    db_session.add_all([enabled_category, disabled_category])
    await db_session.commit()

    missing_category_response = await api_client.post(
        "/api/v1/tools",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "name": "Missing Category Tool",
            "slug": "missing-category-tool",
        },
    )
    assert missing_category_response.status_code == 422

    invalid_category_response = await api_client.post(
        "/api/v1/tools",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "name": "Invalid Category Tool",
            "slug": "invalid-category-tool",
            "category_id": "non-existent-category-id",
        },
    )
    assert invalid_category_response.status_code == 422

    disabled_category_response = await api_client.post(
        "/api/v1/tools",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "name": "Disabled Category Tool",
            "slug": "disabled-category-tool",
            "category_id": disabled_category.id,
        },
    )
    assert disabled_category_response.status_code == 422

    valid_response = await api_client.post(
        "/api/v1/tools",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "name": "Valid Tool",
            "slug": "valid-tool",
            "category_id": enabled_category.id,
        },
    )
    assert valid_response.status_code == 200
    assert valid_response.json()["data"]["category_id"] == enabled_category.id


@pytest.mark.asyncio
async def test_disabled_category_cannot_be_used_for_tool_update(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
):
    """停用分类不能用于编辑工具。"""
    enabled_category = ToolCategory(
        name="Docking",
        slug="docking",
        sort_order=0,
        is_enabled=True,
    )
    disabled_category = ToolCategory(
        name="Disabled",
        slug="disabled",
        sort_order=1,
        is_enabled=False,
    )
    db_session.add_all([enabled_category, disabled_category])
    await db_session.flush()

    tool = Tool(
        owner_id=admin_user.id,
        name="Editable Tool",
        slug="editable-tool",
        description="editable tool",
        category_id=enabled_category.id,
        category=enabled_category.name,
        status=ToolStatus.DRAFT.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.commit()

    response = await api_client.put(
        f"/api/v1/tools/{tool.id}",
        headers={"Authorization": "Bearer admin-token"},
        json={"category_id": disabled_category.id},
    )

    assert response.status_code == 422
