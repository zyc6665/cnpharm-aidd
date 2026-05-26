"""工具分类管理测试。"""

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
from app.models.tools import Tool, ToolStatus
from app.models.users import User, UserRole, UserStatus
from app.schemas import tools as tool_schemas

# 导入模型模块，确保测试库建表时元数据完整。
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import tools as tool_models
from app.models import users as _user_models  # noqa: F401


def get_tool_category_model():
    """获取工具分类模型。"""
    return getattr(tool_models, "ToolCategory", None)


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
async def test_tool_category_model_exists():
    """存在独立的工具分类模型。"""
    tool_category_model = get_tool_category_model()

    assert tool_category_model is not None, "缺少 ToolCategory 模型"
    assert hasattr(Tool, "category_id"), "Tool 缺少 category_id 外键字段"


@pytest.mark.asyncio
async def test_admin_can_create_tool_category(api_client: httpx.AsyncClient):
    """管理员可以创建工具分类。"""
    response = await api_client.post(
        "/api/v1/admin/tool-categories",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "name": "Docking",
            "slug": "docking",
            "description": "Molecular docking tools",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["name"] == "Docking"
    assert payload["data"]["slug"] == "docking"


@pytest.mark.asyncio
async def test_public_categories_only_return_enabled_sorted(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """公开分类列表只返回启用分类并按排序值升序。"""
    tool_category_model = get_tool_category_model()
    assert tool_category_model is not None, "缺少 ToolCategory 模型"

    db_session.add_all([
        tool_category_model(
            name="Visualization",
            slug="visualization",
            sort_order=30,
            is_enabled=True,
        ),
        tool_category_model(
            name="Disabled",
            slug="disabled",
            sort_order=5,
            is_enabled=False,
        ),
        tool_category_model(
            name="Docking",
            slug="docking",
            sort_order=10,
            is_enabled=True,
        ),
    ])
    await db_session.commit()

    response = await api_client.get("/api/v1/tools/categories")

    assert response.status_code == 200
    payload = response.json()
    assert [item["slug"] for item in payload["data"]] == ["docking", "visualization"]


@pytest.mark.asyncio
async def test_non_admin_cannot_create_tool_category(api_client: httpx.AsyncClient):
    """非管理员不允许创建工具分类。"""
    response = await api_client.post(
        "/api/v1/admin/tool-categories",
        headers={"Authorization": "Bearer user-token"},
        json={
            "name": "Docking",
            "slug": "docking",
        },
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_update_status_and_reorder_categories(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """管理员可以更新分类、启停分类并重排。"""
    tool_category_model = get_tool_category_model()
    assert tool_category_model is not None, "缺少 ToolCategory 模型"

    category_a = tool_category_model(
        name="Docking",
        slug="docking",
        sort_order=10,
        is_enabled=True,
    )
    category_b = tool_category_model(
        name="Analysis",
        slug="analysis",
        sort_order=20,
        is_enabled=True,
    )
    db_session.add_all([category_a, category_b])
    await db_session.commit()

    update_response = await api_client.put(
        f"/api/v1/admin/tool-categories/{category_a.id}",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "name": "Docking Updated",
            "description": "updated description",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["name"] == "Docking Updated"

    disable_response = await api_client.patch(
        f"/api/v1/admin/tool-categories/{category_b.id}/status",
        headers={"Authorization": "Bearer admin-token"},
        json={"is_enabled": False},
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["data"]["is_enabled"] is False

    reorder_response = await api_client.post(
        "/api/v1/admin/tool-categories/reorder",
        headers={"Authorization": "Bearer admin-token"},
        json={"category_ids": [category_b.id, category_a.id]},
    )
    assert reorder_response.status_code == 200

    await db_session.refresh(category_a)
    await db_session.refresh(category_b)
    assert (category_b.sort_order, category_a.sort_order) == (0, 1)


@pytest.mark.asyncio
async def test_referenced_tool_category_cannot_be_deleted(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
):
    """已被工具引用的分类不能删除。"""
    tool_category_model = get_tool_category_model()
    assert tool_category_model is not None, "缺少 ToolCategory 模型"

    category = tool_category_model(
        name="Docking",
        slug="docking",
        description="Molecular docking tools",
        sort_order=1,
        is_enabled=True,
    )
    db_session.add(category)
    await db_session.flush()

    tool = Tool(
        owner_id=admin_user.id,
        name="Test Tool",
        slug="test-tool",
        description="tool for category reference",
        category="Docking",
        status=ToolStatus.DRAFT.value,
        is_public=True,
    )
    setattr(tool, "category_id", category.id)
    db_session.add(tool)
    await db_session.commit()

    response = await api_client.delete(
        f"/api/v1/admin/tool-categories/{category.id}",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 409


def test_tool_category_schema_contracts():
    """工具分类相关 Schema 已定义并切换到 category_id。"""
    create_schema = getattr(tool_schemas, "ToolCategoryCreate", None)
    update_schema = getattr(tool_schemas, "ToolCategoryUpdate", None)
    response_schema = getattr(tool_schemas, "ToolCategoryResponse", None)
    status_schema = getattr(tool_schemas, "ToolCategoryStatusUpdate", None)
    reorder_schema = getattr(tool_schemas, "ToolCategoryReorderRequest", None)

    assert create_schema is not None, "缺少 ToolCategoryCreate"
    assert update_schema is not None, "缺少 ToolCategoryUpdate"
    assert response_schema is not None, "缺少 ToolCategoryResponse"
    assert status_schema is not None, "缺少 ToolCategoryStatusUpdate"
    assert reorder_schema is not None, "缺少 ToolCategoryReorderRequest"

    tool_create_fields = tool_schemas.ToolCreate.model_fields
    tool_update_fields = tool_schemas.ToolUpdate.model_fields
    tool_response_fields = tool_schemas.ToolResponse.model_fields
    tool_list_fields = tool_schemas.ToolListResponse.model_fields

    assert "category_id" in tool_create_fields, "ToolCreate 缺少 category_id"
    assert "category_id" in tool_update_fields, "ToolUpdate 缺少 category_id"
    assert "category_id" in tool_response_fields, "ToolResponse 缺少 category_id"
    assert "category" in tool_response_fields, "ToolResponse 缺少兼容展示字段 category"
    assert "category_id" in tool_list_fields, "ToolListResponse 缺少 category_id"
    assert "category" in tool_list_fields, "ToolListResponse 缺少兼容展示字段 category"
