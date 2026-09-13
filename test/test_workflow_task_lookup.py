"""Workflow task lookup tests."""

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
from app.models.tasks import Task, TaskInput, TaskStatus  # noqa: E402
from app.models.users import User  # noqa: E402
from app.models.workflows import WorkflowRun  # noqa: E402
from app.services.workflow_task_lookup import find_existing_workflow_node_task  # noqa: E402


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
async def test_find_existing_workflow_node_task_returns_matching_active_task(
    db_session: AsyncSession,
) -> None:
    user = User(id="user-1", email="u@example.com", password_hash="hash")
    task = Task(
        id="task-1",
        user_id=user.id,
        tool_id="tool-1",
        tool_version_id="version-1",
        name="workflow node task",
        status=TaskStatus.PENDING.value,
    )
    db_session.add_all([
        user,
        task,
        TaskInput(
            task_id=task.id,
            params={"workflow_run_id": "run-1", "workflow_node_id": "node-a"},
            file_ids=[],
        ),
    ])
    await db_session.flush()

    found = await find_existing_workflow_node_task(
        db_session,
        current_user=user,
        run=WorkflowRun(id="run-1"),
        node_id="node-a",
        tool_id="tool-1",
    )

    assert found is not None
    assert found.id == task.id


@pytest.mark.asyncio
async def test_find_existing_workflow_node_task_ignores_failed_tasks(
    db_session: AsyncSession,
) -> None:
    user = User(id="user-1", email="u@example.com", password_hash="hash")
    task = Task(
        id="task-1",
        user_id=user.id,
        tool_id="tool-1",
        tool_version_id="version-1",
        name="failed workflow node task",
        status=TaskStatus.FAILURE.value,
    )
    db_session.add_all([
        user,
        task,
        TaskInput(
            task_id=task.id,
            params={"workflow_run_id": "run-1", "workflow_node_id": "node-a"},
            file_ids=[],
        ),
    ])
    await db_session.flush()

    found = await find_existing_workflow_node_task(
        db_session,
        current_user=user,
        run=WorkflowRun(id="run-1"),
        node_id="node-a",
        tool_id="tool-1",
    )

    assert found is None
