"""Workflow scheduler tool availability tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.exceptions import ValidationException  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.models import agent as _agent_models  # noqa: F401,E402
from app.models import files as _files_models  # noqa: F401,E402
from app.models import statistics as _statistics_models  # noqa: F401,E402
from app.models import system_settings as _system_settings  # noqa: F401,E402
from app.models import tasks as _task_models  # noqa: F401,E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models import users as _users_models  # noqa: F401,E402
from app.models.tools import Tool, ToolProviderType, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.services.workflow_scheduler import load_available_workflow_tool  # noqa: E402


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    user = User(
        email="workflow-owner@example.com",
        password_hash="hashed-password",
        display_name="workflow-owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _create_tool(
    db_session: AsyncSession,
    owner: User,
    *,
    slug: str,
    provider_type: str,
    executor_type: str,
    is_public: bool = False,
    is_active: bool = True,
    deprecated: bool = False,
) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name=slug,
        slug=slug,
        status=ToolStatus.PUBLISHED.value,
        is_public=is_public,
        provider_type=provider_type,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={"type": executor_type},
        is_active=is_active,
        deprecated=deprecated,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    return tool


@pytest.mark.asyncio
async def test_private_platform_builtin_is_available_to_workflow(
    db_session: AsyncSession,
    owner: User,
) -> None:
    tool = await _create_tool(
        db_session,
        owner,
        slug="builtin-sdf-to-pdb",
        provider_type=ToolProviderType.PLATFORM.value,
        executor_type="builtin",
    )

    loaded = await load_available_workflow_tool(db_session, node={"tool_id": tool.id})

    assert loaded.id == tool.id


@pytest.mark.asyncio
async def test_private_user_tool_remains_unavailable_to_workflow(
    db_session: AsyncSession,
    owner: User,
) -> None:
    tool = await _create_tool(
        db_session,
        owner,
        slug="private-user-tool",
        provider_type=ToolProviderType.USER.value,
        executor_type="builtin",
    )

    with pytest.raises(ValidationException, match="Workflow tool is unavailable"):
        await load_available_workflow_tool(db_session, node={"tool_id": tool.id})


@pytest.mark.asyncio
async def test_deprecated_platform_builtin_is_unavailable_to_workflow(
    db_session: AsyncSession,
    owner: User,
) -> None:
    tool = await _create_tool(
        db_session,
        owner,
        slug="builtin-deprecated",
        provider_type=ToolProviderType.PLATFORM.value,
        executor_type="builtin",
        is_public=True,
        deprecated=True,
    )

    with pytest.raises(ValidationException, match="Workflow tool has no active version"):
        await load_available_workflow_tool(db_session, node={"tool_id": tool.id})
