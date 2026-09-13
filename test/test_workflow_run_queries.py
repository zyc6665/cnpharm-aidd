"""Workflow run query helper tests."""

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

from app.database.base import Base  # noqa: E402
from app.models import users as _users_models  # noqa: F401,E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.models.workflows import WorkflowDefinition, WorkflowRun  # noqa: E402
from app.services.workflow_run_queries import load_run_for_user  # noqa: E402


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


@pytest.mark.asyncio
async def test_load_run_for_user_allows_projectless_owner(db_session: AsyncSession):
    user = User(
        email="workflow-query-owner@example.com",
        password_hash="hashed-password",
        display_name="owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.flush()

    workflow = WorkflowDefinition(
        user_id=user.id,
        name="Query workflow",
        canvas_preset_id="custom",
        nodes=[],
        edges=[],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = WorkflowRun(
        owner_id=user.id,
        workflow_definition_id=workflow.id,
        name="Query run",
        definition={"nodes": [], "edges": []},
        input_files={},
        execution_order=[],
        node_states={},
        artifact_lineage={},
    )
    db_session.add(run)
    await db_session.commit()

    loaded = await load_run_for_user(db_session, run_id=run.id, current_user=user)

    assert loaded.id == run.id
