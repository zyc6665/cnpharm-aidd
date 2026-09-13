"""Workflow tool lookup tests."""

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
from app.models.tools import Tool, ToolProviderType, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User  # noqa: E402
from app.services.workflow_tool_lookup import load_available_workflow_tool  # noqa: E402


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


async def _create_tool(
    db_session: AsyncSession,
    *,
    slug: str,
    provider_type: str,
    is_public: bool = False,
    config: dict | None = None,
) -> Tool:
    owner = User(id=f"owner-{slug}", email=f"{slug}@example.com", password_hash="hash")
    tool = Tool(
        owner_id=owner.id,
        name=slug,
        slug=slug,
        status=ToolStatus.PUBLISHED.value,
        is_public=is_public,
        provider_type=provider_type,
    )
    db_session.add_all([owner, tool])
    await db_session.flush()

    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config=config or {"type": "builtin"},
        is_active=True,
        deprecated=False,
    )
    db_session.add(version)
    await db_session.flush()

    tool.current_version_id = version.id
    await db_session.commit()
    return tool


@pytest.mark.asyncio
async def test_load_available_workflow_tool_allows_private_platform_builtin(
    db_session: AsyncSession,
) -> None:
    tool = await _create_tool(
        db_session,
        slug="builtin-tool",
        provider_type=ToolProviderType.PLATFORM.value,
        config={"type": "builtin"},
    )

    loaded = await load_available_workflow_tool(db_session, node={"tool_slug": tool.slug})

    assert loaded.id == tool.id


@pytest.mark.asyncio
async def test_load_available_workflow_tool_rejects_private_user_tool(
    db_session: AsyncSession,
) -> None:
    tool = await _create_tool(
        db_session,
        slug="private-user-tool",
        provider_type=ToolProviderType.USER.value,
        config={"type": "builtin"},
    )

    with pytest.raises(ValidationException, match="Workflow tool is unavailable"):
        await load_available_workflow_tool(db_session, node={"tool_slug": tool.slug})
