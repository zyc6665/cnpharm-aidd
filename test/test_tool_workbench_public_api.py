"""前台工作台分组公开接口测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.dependencies import get_current_user_optional
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
    ToolProviderType,
    ToolStatus,
    ToolVersion,
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
async def owner_user(db_session: AsyncSession) -> User:
    """创建工具归属用户。"""
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


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
):
    """创建带依赖覆盖的公开 API 客户端。"""

    async def override_get_db():
        yield db_session

    async def override_get_current_user_optional() -> None:
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def tool_category(
    db_session: AsyncSession,
) -> ToolCategory:
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


async def create_tool(
    db_session: AsyncSession,
    owner_user: User,
    tool_category: ToolCategory,
    *,
    name: str,
    slug: str,
    status: ToolStatus = ToolStatus.PUBLISHED,
    is_public: bool = True,
) -> Tool:
    """创建工具记录。"""
    tool = Tool(
        owner_id=owner_user.id,
        name=name,
        slug=slug,
        description=f"{name} description",
        category_id=tool_category.id,
        category=tool_category.name,
        status=status.value,
        is_public=is_public,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


async def attach_tool_version(
    db_session: AsyncSession,
    tool: Tool,
    config: dict,
) -> ToolVersion:
    """为公开工具附加当前版本。"""
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        changelog="Initial version",
        config=config,
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return version


@pytest.mark.asyncio
async def test_public_workbench_groups_returns_enabled_groups(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """公开接口只返回启用的工作台分组。"""
    first_group = ToolWorkbenchGroup(
        name="Pocket",
        slug="pocket",
        description="Pocket tools",
        sort_order=1,
        is_enabled=True,
    )
    enabled_group = ToolWorkbenchGroup(
        name="Docking",
        slug="docking",
        description="Docking tools",
        sort_order=2,
        is_enabled=True,
    )
    disabled_group = ToolWorkbenchGroup(
        name="Analysis",
        slug="analysis",
        description="Analysis tools",
        sort_order=3,
        is_enabled=False,
    )
    db_session.add_all([first_group, enabled_group, disabled_group])
    await db_session.commit()

    response = await api_client.get("/api/v1/tools/workbench-groups")

    assert response.status_code == 200
    payload = response.json()
    assert [group["slug"] for group in payload["data"]] == ["pocket", "docking"]
    assert payload["data"][0]["name"] == "Pocket"


@pytest.mark.asyncio
async def test_public_tool_list_includes_valid_workflow_contract(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner_user: User,
    tool_category: ToolCategory,
):
    """公开工具列表应返回前端单节点运行预检所需契约。"""
    tool = await create_tool(
        db_session,
        owner_user,
        tool_category,
        name="Fetch PDB Structure",
        slug="builtin-fetch-pdb",
    )
    await attach_tool_version(
        db_session,
        tool,
        {
            "type": "builtin",
            "builtin_slug": "builtin-fetch-pdb",
            "timeout_sec": 120,
            "input_schema": {
                "type": "object",
                "properties": {"pdb_id": {"type": "string"}},
                "required": ["pdb_id"],
            },
            "agent_capability": {
                "enabled": True,
                "stage": "data_acquisition",
                "capability": "external_database_fetch",
                "inputs": [],
                "outputs": [
                    {
                        "semantic_type": "protein_structure@1",
                        "source": "artifact",
                        "path": "protein",
                        "required": True,
                    }
                ],
                "defaults": {},
            },
            "artifacts": {
                "inputs": [],
                "outputs": [
                    {"name": "protein", "type": "protein_structure@1", "required": True},
                    {"name": "report", "type": "run_report@1", "required": False},
                ],
            },
        },
    )

    response = await api_client.get("/api/v1/tools", params={"view": "public"})

    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["slug"] == "builtin-fetch-pdb"
    assert item["contract"]["validation"] == {"status": "valid", "errors": []}
    assert item["contract"]["artifacts"]["outputs"][0] == {
        "name": "protein",
        "type": "protein_structure@1",
        "cardinality": "one",
        "required": True,
    }


@pytest.mark.asyncio
async def test_public_tool_list_and_detail_include_platform_tools_without_public_flag(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner_user: User,
    tool_category: ToolCategory,
):
    """平台工具按部署归属公开，不能因 is_public 历史值隐藏。"""
    tool = await create_tool(
        db_session,
        owner_user,
        tool_category,
        name="Builtin Protein Preparation",
        slug="builtin-protein-preparation",
        is_public=False,
    )
    tool.provider_type = ToolProviderType.PLATFORM.value
    await attach_tool_version(
        db_session,
        tool,
        {
            "type": "builtin",
            "builtin_slug": "builtin-protein-preparation",
            "agent_capability": {
                "enabled": True,
                "stage": "protein_preparation",
                "capability": "protein_preparation",
                "inputs": [],
                "outputs": [],
                "defaults": {},
            },
        },
    )

    list_response = await api_client.get("/api/v1/tools", params={"view": "public"})
    assert list_response.status_code == 200
    list_item = list_response.json()["data"]["items"][0]
    assert list_item["slug"] == "builtin-protein-preparation"
    assert list_item["deployment"] == {
        "kind": "platform_builtin",
        "executor_type": "builtin",
    }

    detail_response = await api_client.get(f"/api/v1/tools/{tool.id}")
    assert detail_response.status_code == 200
    detail_item = detail_response.json()["data"]
    assert detail_item["slug"] == "builtin-protein-preparation"
    assert detail_item["deployment"] == {
        "kind": "platform_builtin",
        "executor_type": "builtin",
    }


@pytest.mark.asyncio
async def test_public_workbench_groups_only_returns_visible_tools_in_each_group(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner_user: User,
    tool_category: ToolCategory,
):
    """组内只返回当前可见工具。"""
    group = ToolWorkbenchGroup(
        name="Docking",
        slug="docking",
        description="Docking tools",
        sort_order=1,
        is_enabled=True,
    )
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    visible_tool = await create_tool(
        db_session,
        owner_user,
        tool_category,
        name="Visible Tool",
        slug="visible-tool",
    )
    visible_tool.provider_type = ToolProviderType.PLATFORM.value
    await attach_tool_version(
        db_session,
        visible_tool,
        {"type": "builtin", "builtin_slug": "visible-tool"},
    )
    private_tool = await create_tool(
        db_session,
        owner_user,
        tool_category,
        name="Private Tool",
        slug="private-tool",
        is_public=False,
    )
    draft_tool = await create_tool(
        db_session,
        owner_user,
        tool_category,
        name="Draft Tool",
        slug="draft-tool",
        status=ToolStatus.DRAFT,
    )
    disabled_mapping_tool = await create_tool(
        db_session,
        owner_user,
        tool_category,
        name="Disabled Mapping Tool",
        slug="disabled-mapping-tool",
    )

    db_session.add_all(
        [
            ToolWorkbenchGroupMapping(
                tool_id=visible_tool.id,
                group_id=group.id,
                sort_order=0,
                is_enabled=True,
            ),
            ToolWorkbenchGroupMapping(
                tool_id=private_tool.id,
                group_id=group.id,
                sort_order=1,
                is_enabled=True,
            ),
            ToolWorkbenchGroupMapping(
                tool_id=draft_tool.id,
                group_id=group.id,
                sort_order=2,
                is_enabled=True,
            ),
            ToolWorkbenchGroupMapping(
                tool_id=disabled_mapping_tool.id,
                group_id=group.id,
                sort_order=3,
                is_enabled=False,
            ),
        ]
    )
    await db_session.commit()

    response = await api_client.get("/api/v1/tools/workbench-groups")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["data"]) == 1
    assert payload["data"][0]["slug"] == "docking"
    assert [tool["slug"] for tool in payload["data"][0]["tools"]] == ["visible-tool"]
    assert payload["data"][0]["tools"][0]["deployment"] == {
        "kind": "platform_builtin",
        "executor_type": "builtin",
    }


@pytest.mark.asyncio
async def test_public_workbench_groups_preserves_recommendation_flag_and_mapping_order(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner_user: User,
    tool_category: ToolCategory,
):
    """组内工具返回映射推荐标记并按映射排序。"""
    group = ToolWorkbenchGroup(
        name="Docking",
        slug="docking",
        description="Docking tools",
        sort_order=1,
        is_enabled=True,
    )
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    recommended_tool = await create_tool(
        db_session,
        owner_user,
        tool_category,
        name="Recommended Tool",
        slug="recommended-tool",
    )
    regular_tool = await create_tool(
        db_session,
        owner_user,
        tool_category,
        name="Regular Tool",
        slug="regular-tool",
    )

    db_session.add_all(
        [
            ToolWorkbenchGroupMapping(
                tool_id=recommended_tool.id,
                group_id=group.id,
                sort_order=1,
                is_recommended=True,
                is_enabled=True,
            ),
            ToolWorkbenchGroupMapping(
                tool_id=regular_tool.id,
                group_id=group.id,
                sort_order=0,
                is_recommended=False,
                is_enabled=True,
            ),
        ]
    )
    await db_session.commit()

    response = await api_client.get("/api/v1/tools/workbench-groups")

    assert response.status_code == 200
    payload = response.json()
    tools = payload["data"][0]["tools"]
    assert [tool["slug"] for tool in tools] == ["regular-tool", "recommended-tool"]
    assert tools[0]["is_recommended"] is False
    assert tools[1]["is_recommended"] is True
