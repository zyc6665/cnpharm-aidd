"""Workflow map item resolution tests."""

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
from app.models.workflows import WorkflowRun  # noqa: E402
from app.services.workflow_map_items import resolve_map_items  # noqa: E402


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
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


@pytest.mark.asyncio
async def test_resolve_map_items_reads_workflow_input_list(db_session: AsyncSession) -> None:
    run = WorkflowRun(input_files={"items": ["a", "b", "c"]})

    result = await resolve_map_items(
        db_session,
        over="workflow_input:items",
        run=run,
        node_states={},
    )

    assert result == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_resolve_map_items_rejects_unknown_reference(db_session: AsyncSession) -> None:
    with pytest.raises(ValidationException, match="Unsupported map over"):
        await resolve_map_items(
            db_session,
            over="unknown:items",
            run=WorkflowRun(input_files={}),
            node_states={},
        )
