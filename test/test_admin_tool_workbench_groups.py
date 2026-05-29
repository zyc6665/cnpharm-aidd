"""管理员工作台分组与映射权限测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy.exc import IntegrityError
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
from app.models.tools import (
    Tool,
    ToolCategory,
    ToolStatus,
    ToolWorkbenchGroup,
    ToolWorkbenchGroupMapping,
)
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


@pytest_asyncio.fixture
async def tool_category(db_session: AsyncSession) -> ToolCategory:
    """创建工具分类。"""
    category = ToolCategory(
        name="Docking",
        slug="docking",
        sort_order=0,
        is_enabled=True,
    )
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    return category


@pytest_asyncio.fixture
async def tool_record(
    db_session: AsyncSession,
    admin_user: User,
    tool_category: ToolCategory,
) -> Tool:
    """创建工具记录。"""
    tool = Tool(
        owner_id=admin_user.id,
        name="Workbench Tool",
        slug="workbench-tool",
        description="tool for workbench group tests",
        category_id=tool_category.id,
        category=tool_category.name,
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest_asyncio.fixture
async def existing_groups(db_session: AsyncSession) -> tuple[ToolWorkbenchGroup, ToolWorkbenchGroup]:
    """创建待重排的工作台分组。"""
    group_a = ToolWorkbenchGroup(
        name="Docking",
        slug="docking",
        description="Docking tools",
        sort_order=10,
        is_enabled=True,
    )
    group_b = ToolWorkbenchGroup(
        name="Analysis",
        slug="analysis",
        description="Analysis tools",
        sort_order=20,
        is_enabled=True,
    )
    db_session.add_all([group_a, group_b])
    await db_session.commit()
    await db_session.refresh(group_a)
    await db_session.refresh(group_b)
    return group_a, group_b


@pytest.mark.asyncio
async def test_admin_can_create_workbench_group(
    api_client: httpx.AsyncClient,
):
    """管理员可以创建工作台分组。"""
    create_response = await api_client.post(
        "/api/v1/admin/workbench-groups",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "name": "Visualization",
            "slug": "visualization",
            "description": "Visualization tools",
            "sort_order": 30,
            "is_enabled": True,
        },
    )

    assert create_response.status_code == 200
    created_payload = create_response.json()
    assert created_payload["data"]["name"] == "Visualization"
    assert created_payload["data"]["slug"] == "visualization"
    assert created_payload["data"]["description"] == "Visualization tools"
    assert created_payload["data"]["sort_order"] == 30
    assert created_payload["data"]["is_enabled"] is True


@pytest.mark.asyncio
async def test_admin_can_update_workbench_group(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    existing_groups: tuple[ToolWorkbenchGroup, ToolWorkbenchGroup],
):
    """管理员可以更新工作台分组。"""
    group_a, _ = existing_groups

    update_response = await api_client.put(
        f"/api/v1/admin/workbench-groups/{group_a.id}",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "name": "Docking Updated",
            "description": "Updated docking tools",
            "is_enabled": False,
        },
    )

    assert update_response.status_code == 200
    updated_payload = update_response.json()
    assert updated_payload["data"]["name"] == "Docking Updated"
    assert updated_payload["data"]["description"] == "Updated docking tools"
    assert updated_payload["data"]["is_enabled"] is False

    await db_session.refresh(group_a)
    assert group_a.name == "Docking Updated"
    assert group_a.description == "Updated docking tools"
    assert group_a.is_enabled is False


@pytest.mark.asyncio
async def test_admin_can_update_workbench_group_with_existing_sort_order_value(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    existing_groups: tuple[ToolWorkbenchGroup, ToolWorkbenchGroup],
):
    """管理员回传现有排序值更新分组时不应触发重排校验失败。"""
    group_a, _ = existing_groups

    update_response = await api_client.put(
        f"/api/v1/admin/workbench-groups/{group_a.id}",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "name": "Docking Roundtrip",
            "sort_order": group_a.sort_order,
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["data"]["sort_order"] == group_a.sort_order

    await db_session.refresh(group_a)
    assert group_a.name == "Docking Roundtrip"
    assert group_a.sort_order == 10


@pytest.mark.asyncio
async def test_admin_can_reorder_workbench_groups(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    existing_groups: tuple[ToolWorkbenchGroup, ToolWorkbenchGroup],
):
    """管理员可以排序工作台分组。"""
    group_a, group_b = existing_groups

    reorder_response = await api_client.post(
        "/api/v1/admin/workbench-groups/reorder",
        headers={"Authorization": "Bearer admin-token"},
        json={"group_ids": [group_b.id, group_a.id]},
    )

    assert reorder_response.status_code == 200

    await db_session.refresh(group_a)
    await db_session.refresh(group_b)
    assert (group_b.sort_order, group_a.sort_order) == (0, 1)


@pytest.mark.asyncio
async def test_admin_can_delete_empty_workbench_group(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    existing_groups: tuple[ToolWorkbenchGroup, ToolWorkbenchGroup],
):
    """管理员可以删除没有映射的工作台分组。"""
    _, group_b = existing_groups

    delete_response = await api_client.delete(
        f"/api/v1/admin/workbench-groups/{group_b.id}",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert delete_response.status_code == 200
    assert await db_session.get(ToolWorkbenchGroup, group_b.id) is None


@pytest.mark.asyncio
async def test_admin_cannot_delete_workbench_group_with_mappings(
    api_client: httpx.AsyncClient,
    existing_groups: tuple[ToolWorkbenchGroup, ToolWorkbenchGroup],
    existing_mapping: ToolWorkbenchGroupMapping,
):
    """管理员不能删除仍有关联映射的工作台分组。"""
    group_a, _ = existing_groups

    delete_response = await api_client.delete(
        f"/api/v1/admin/workbench-groups/{group_a.id}",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert delete_response.status_code == 409
    assert delete_response.json()["message"] == "工作台分组下仍有关联工具，无法删除"


@pytest.mark.asyncio
async def test_admin_can_create_workbench_group_mapping(
    api_client: httpx.AsyncClient,
    tool_record: Tool,
    existing_groups: tuple[ToolWorkbenchGroup, ToolWorkbenchGroup],
):
    """管理员可以创建工作台分组映射。"""
    group_a, _ = existing_groups

    create_response = await api_client.post(
        "/api/v1/admin/workbench-group-mappings",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": tool_record.id,
            "group_id": group_a.id,
            "sort_order": 5,
            "is_recommended": True,
            "is_enabled": True,
        },
    )

    assert create_response.status_code == 200
    created_payload = create_response.json()
    assert created_payload["data"]["tool_id"] == tool_record.id
    assert created_payload["data"]["group_id"] == group_a.id
    assert created_payload["data"]["sort_order"] == 5
    assert created_payload["data"]["is_recommended"] is True
    assert created_payload["data"]["is_enabled"] is True


@pytest_asyncio.fixture
async def existing_mapping(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    tool_record: Tool,
    existing_groups: tuple[ToolWorkbenchGroup, ToolWorkbenchGroup],
) -> ToolWorkbenchGroupMapping:
    """创建已有工作台分组映射。"""
    group_a, group_b = existing_groups

    mapping = ToolWorkbenchGroupMapping(
        tool_id=tool_record.id,
        group_id=group_a.id,
        sort_order=5,
        is_recommended=True,
        is_enabled=True,
    )
    db_session.add(mapping)
    await db_session.commit()
    await db_session.refresh(mapping)
    return mapping


@pytest.mark.asyncio
async def test_admin_create_workbench_group_mapping_translates_integrity_error_to_conflict(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tool_record: Tool,
    existing_groups: tuple[ToolWorkbenchGroup, ToolWorkbenchGroup],
):
    """数据库唯一冲突应转换为 409 响应。"""
    group_a, _ = existing_groups

    async def raise_integrity_error():
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(db_session, "commit", raise_integrity_error)

    response = await api_client.post(
        "/api/v1/admin/workbench-group-mappings",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": tool_record.id,
            "group_id": group_a.id,
            "sort_order": 0,
        },
    )

    assert response.status_code == 409
    assert response.json()["message"] == "工具与工作台分组映射已存在"


@pytest.mark.asyncio
async def test_admin_can_update_workbench_group_mapping(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    existing_groups: tuple[ToolWorkbenchGroup, ToolWorkbenchGroup],
    existing_mapping: ToolWorkbenchGroupMapping,
):
    """管理员可以更新工作台分组映射。"""
    _, group_b = existing_groups

    update_response = await api_client.put(
        f"/api/v1/admin/workbench-group-mappings/{existing_mapping.id}",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "group_id": group_b.id,
            "sort_order": 0,
            "is_recommended": False,
            "is_enabled": False,
        },
    )

    assert update_response.status_code == 200
    updated_payload = update_response.json()
    assert updated_payload["data"]["group_id"] == group_b.id
    assert updated_payload["data"]["sort_order"] == 0
    assert updated_payload["data"]["is_recommended"] is False
    assert updated_payload["data"]["is_enabled"] is False

    await db_session.refresh(existing_mapping)
    assert existing_mapping.group_id == group_b.id
    assert existing_mapping.sort_order == 0
    assert existing_mapping.is_recommended is False
    assert existing_mapping.is_enabled is False


@pytest.mark.asyncio
async def test_admin_can_update_workbench_group_mapping_with_existing_sort_order_value(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    existing_mapping: ToolWorkbenchGroupMapping,
):
    """管理员回传现有映射排序值更新其他字段时不应被拒绝。"""
    update_response = await api_client.put(
        f"/api/v1/admin/workbench-group-mappings/{existing_mapping.id}",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "sort_order": existing_mapping.sort_order,
            "is_enabled": False,
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["data"]["sort_order"] == existing_mapping.sort_order
    assert payload["data"]["is_enabled"] is False

    await db_session.refresh(existing_mapping)
    assert existing_mapping.sort_order == 5
    assert existing_mapping.is_enabled is False


@pytest.mark.asyncio
async def test_admin_can_delete_workbench_group_mapping(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    existing_mapping: ToolWorkbenchGroupMapping,
):
    """管理员可以删除工作台分组映射。"""
    delete_response = await api_client.delete(
        f"/api/v1/admin/workbench-group-mappings/{existing_mapping.id}",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert delete_response.status_code == 200

    deleted_mapping = await db_session.get(ToolWorkbenchGroupMapping, existing_mapping.id)
    assert deleted_mapping is None


@pytest.mark.asyncio
async def test_admin_delete_workbench_group_mapping_resequences_remaining_items(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    tool_record: Tool,
    existing_groups: tuple[ToolWorkbenchGroup, ToolWorkbenchGroup],
):
    """删除分组映射后应重排保留映射的顺序。"""
    group_a, _ = existing_groups
    first_mapping = ToolWorkbenchGroupMapping(
        tool_id=tool_record.id,
        group_id=group_a.id,
        sort_order=0,
        is_enabled=True,
    )
    second_tool = Tool(
        owner_id=tool_record.owner_id,
        name="Second Workbench Tool",
        slug="second-workbench-tool",
        description="second tool for resequence tests",
        category_id=tool_record.category_id,
        category=tool_record.category,
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add_all([first_mapping, second_tool])
    await db_session.commit()
    await db_session.refresh(second_tool)

    second_mapping = ToolWorkbenchGroupMapping(
        tool_id=second_tool.id,
        group_id=group_a.id,
        sort_order=1,
        is_enabled=True,
    )
    db_session.add(second_mapping)
    await db_session.commit()
    await db_session.refresh(first_mapping)
    await db_session.refresh(second_mapping)

    delete_response = await api_client.delete(
        f"/api/v1/admin/workbench-group-mappings/{first_mapping.id}",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert delete_response.status_code == 200
    await db_session.refresh(second_mapping)
    assert second_mapping.sort_order == 0


@pytest.mark.asyncio
async def test_admin_rejects_sparse_sort_order_when_moving_mapping_to_empty_group(
    api_client: httpx.AsyncClient,
    existing_groups: tuple[ToolWorkbenchGroup, ToolWorkbenchGroup],
    existing_mapping: ToolWorkbenchGroupMapping,
):
    """迁移到空分组时不应接受超范围排序值。"""
    _, group_b = existing_groups

    update_response = await api_client.put(
        f"/api/v1/admin/workbench-group-mappings/{existing_mapping.id}",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "group_id": group_b.id,
            "sort_order": 2,
        },
    )

    assert update_response.status_code == 422
    assert update_response.json()["message"] == "工作台分组映射排序值超出范围"


@pytest.mark.asyncio
async def test_admin_rejects_sparse_sort_order_for_single_mapping_in_same_group(
    api_client: httpx.AsyncClient,
    existing_mapping: ToolWorkbenchGroupMapping,
):
    """组内仅剩当前映射时不应接受超范围排序值。"""
    update_response = await api_client.put(
        f"/api/v1/admin/workbench-group-mappings/{existing_mapping.id}",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "sort_order": 3,
        },
    )

    assert update_response.status_code == 422
    assert update_response.json()["message"] == "工作台分组映射排序值超出范围"


@pytest.mark.asyncio
async def test_non_admin_cannot_access_workbench_group_admin_endpoints(
    api_client: httpx.AsyncClient,
    tool_record: Tool,
    existing_groups: tuple[ToolWorkbenchGroup, ToolWorkbenchGroup],
    existing_mapping: ToolWorkbenchGroupMapping,
):
    """非管理员不能访问工作台分组管理接口。"""
    group_a, _ = existing_groups

    list_groups_response = await api_client.get(
        "/api/v1/admin/workbench-groups",
        headers={"Authorization": "Bearer user-token"},
    )
    assert list_groups_response.status_code == 403

    create_group_response = await api_client.post(
        "/api/v1/admin/workbench-groups",
        headers={"Authorization": "Bearer user-token"},
        json={
            "name": "User Group",
            "slug": "user-group",
        },
    )
    assert create_group_response.status_code == 403

    update_group_response = await api_client.put(
        f"/api/v1/admin/workbench-groups/{group_a.id}",
        headers={"Authorization": "Bearer user-token"},
        json={"name": "Should Fail"},
    )
    assert update_group_response.status_code == 403

    reorder_groups_response = await api_client.post(
        "/api/v1/admin/workbench-groups/reorder",
        headers={"Authorization": "Bearer user-token"},
        json={"group_ids": [group_a.id]},
    )
    assert reorder_groups_response.status_code == 403

    delete_group_response = await api_client.delete(
        f"/api/v1/admin/workbench-groups/{group_a.id}",
        headers={"Authorization": "Bearer user-token"},
    )
    assert delete_group_response.status_code == 403

    create_mapping_response = await api_client.post(
        "/api/v1/admin/workbench-group-mappings",
        headers={"Authorization": "Bearer user-token"},
        json={
            "tool_id": tool_record.id,
            "group_id": group_a.id,
        },
    )
    assert create_mapping_response.status_code == 403

    update_mapping_response = await api_client.put(
        f"/api/v1/admin/workbench-group-mappings/{existing_mapping.id}",
        headers={"Authorization": "Bearer user-token"},
        json={"sort_order": 10},
    )
    assert update_mapping_response.status_code == 403

    delete_mapping_response = await api_client.delete(
        f"/api/v1/admin/workbench-group-mappings/{existing_mapping.id}",
        headers={"Authorization": "Bearer user-token"},
    )
    assert delete_mapping_response.status_code == 403
