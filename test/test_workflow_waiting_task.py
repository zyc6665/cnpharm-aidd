"""Workflow waiting task resolution tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models.tasks import Task, TaskOutput, TaskStatus  # noqa: E402
from app.services.workflow_waiting_task import load_finished_workflow_node_task  # noqa: E402


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
async def test_load_finished_workflow_node_task_marks_missing_task_id_failed(
    db_session: AsyncSession,
) -> None:
    run = SimpleNamespace(status="waiting_task", error_message=None, finished_at=None)
    state = {"status": "waiting_task"}
    node_states = {"node-a": state}

    task = await load_finished_workflow_node_task(
        db_session,
        run=run,
        node_states=node_states,
        node_id="node-a",
        state=state,
    )

    assert task is None
    assert run.status == "failure"
    assert state["status"] == "failure"
    assert state["error_message"] == "Workflow node is waiting without a task id"


@pytest.mark.asyncio
async def test_load_finished_workflow_node_task_returns_success_task_with_outputs(
    db_session: AsyncSession,
) -> None:
    db_session.add(
        Task(
            id="task-1",
            tool_id="tool-1",
            tool_version_id="version-1",
            status=TaskStatus.SUCCESS.value,
        )
    )
    db_session.add(TaskOutput(task_id="task-1", result={"ok": True}, file_ids=["file-1"]))
    await db_session.flush()
    run = SimpleNamespace(status="waiting_task", error_message=None, finished_at=None)
    state = {"status": "waiting_task", "task_id": "task-1"}
    node_states = {"node-a": state}

    task = await load_finished_workflow_node_task(
        db_session,
        run=run,
        node_states=node_states,
        node_id="node-a",
        state=state,
    )

    assert task is not None
    assert task.id == "task-1"
    assert task.outputs.result == {"ok": True}
    assert run.status == "waiting_task"
    assert state["status"] == "waiting_task"
