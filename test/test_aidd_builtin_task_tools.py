"""Persisted platform tools for supported AIDD built-ins."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / 'backend'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models import users as _users_models  # noqa: F401,E402
from app.models.tools import ToolStatus  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        'sqlite+aiosqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def system_user(db_session: AsyncSession) -> User:
    user = User(
        email='aidd-system@example.com',
        password_hash='hashed-password',
        role=UserRole.ADMIN.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_ensure_aidd_builtin_tool_creates_published_platform_tool(
    db_session: AsyncSession,
    system_user: User,
) -> None:
    from app.services.aidd_builtin_tools import ensure_aidd_builtin_tool

    tool = await ensure_aidd_builtin_tool(
        db_session,
        owner_id=system_user.id,
        tool_slug='builtin-vina-docking',
    )

    assert tool.owner_id == system_user.id
    assert tool.status == ToolStatus.PUBLISHED.value
    assert tool.current_version is not None
    assert tool.current_version.config['type'] == 'builtin'
    assert tool.current_version.config['builtin_slug'] == 'builtin-vina-docking'


@pytest.mark.asyncio
async def test_ensure_aidd_builtin_tool_is_idempotent(
    db_session: AsyncSession,
    system_user: User,
) -> None:
    from app.services.aidd_builtin_tools import ensure_aidd_builtin_tool

    first = await ensure_aidd_builtin_tool(
        db_session, owner_id=system_user.id, tool_slug='builtin-sdf-to-pdb'
    )
    second = await ensure_aidd_builtin_tool(
        db_session, owner_id=system_user.id, tool_slug='builtin-sdf-to-pdb'
    )

    assert second.id == first.id


@pytest.mark.asyncio
async def test_ensure_protein_preparation_builtin_declares_standard_artifacts(
    db_session: AsyncSession,
    system_user: User,
) -> None:
    from app.services.aidd_builtin_tools import ensure_aidd_builtin_tool

    tool = await ensure_aidd_builtin_tool(
        db_session,
        owner_id=system_user.id,
        tool_slug='builtin-protein-preparation',
    )

    config = tool.current_version.config
    assert config['type'] == 'builtin'
    assert config['builtin_slug'] == 'builtin-protein-preparation'
    assert config['artifacts']['inputs'] == [
        {'name': 'protein', 'type': 'protein_structure@1', 'required': True}
    ]
    assert config['artifacts']['outputs'] == [
        {'name': 'prepared_protein', 'type': 'protein_structure@1', 'required': True}
    ]
