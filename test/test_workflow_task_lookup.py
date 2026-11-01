"""Workflow task lookup tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.models.tasks import Task, TaskInput, TaskStatus  # noqa: E402
from app.models.users import User  # noqa: E402
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


def _task(
    *,
    task_id: str,
    status: str,
    run_id: str = "run-1",
    node_id: str = "node-a",
    attempt: int = 1,
) -> Task:
    return Task(
        id=task_id,
        user_id="user-1",
        tool_id="tool-1",
        tool_version_id="version-1",
        name="workflow node task",
        status=status,
        workflow_run_id=run_id,
        workflow_node_id=node_id,
        workflow_node_attempt=attempt,
    )


@pytest.mark.asyncio
async def test_find_existing_workflow_node_task_returns_matching_active_task(
    db_session: AsyncSession,
) -> None:
    user = User(id="user-1", email="u@example.com", password_hash="hash")
    task = _task(task_id="task-1", status=TaskStatus.PENDING.value)
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
        run_id="run-1",
        node_id="node-a",
    )

    assert found is not None
    assert found.id == task.id


@pytest.mark.asyncio
async def test_find_existing_workflow_node_task_ignores_failed_tasks(
    db_session: AsyncSession,
) -> None:
    user = User(id="user-1", email="u@example.com", password_hash="hash")
    task = _task(task_id="task-1", status=TaskStatus.FAILURE.value)
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
        run_id="run-1",
        node_id="node-a",
    )

    assert found is None


@pytest.mark.asyncio
async def test_duplicate_workflow_node_attempt_is_rejected_by_unique_index(
    db_session: AsyncSession,
) -> None:
    """同一 run+node+attempt 的第二条任务必须被数据库唯一索引拒绝。"""
    user = User(id="user-1", email="u@example.com", password_hash="hash")
    db_session.add(user)
    db_session.add(_task(task_id="task-1", status=TaskStatus.PENDING.value))
    await db_session.flush()

    db_session.add(_task(task_id="task-2", status=TaskStatus.PENDING.value))
    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_lookup_claims_legacy_task_without_snapshot_columns(
    db_session: AsyncSession,
) -> None:
    """三列为 NULL 的历史任务要能被按 params 找回并就地认领。

    迁移 20261030_06 只给每组 (run, node) 里的一条行回填；同组若有多条非终态重复行，
    落选者三列留 NULL，没有回退查询它们就成了查不到但仍会继续跑的僵尸任务。
    """
    user = User(id="user-1", email="u@example.com", password_hash="hash")
    legacy = _task(
        task_id="legacy-1",
        status=TaskStatus.RUNNING.value,
        run_id=None,
        node_id=None,
        attempt=None,
    )
    db_session.add_all([
        user,
        legacy,
        TaskInput(
            task_id=legacy.id,
            params={"workflow_run_id": "run-1", "workflow_node_id": "node-a"},
            file_ids=[],
        ),
    ])
    await db_session.flush()

    found = await find_existing_workflow_node_task(db_session, run_id="run-1", node_id="node-a")
    assert found is not None
    assert found.id == legacy.id
    claimed = await db_session.get(Task, legacy.id, populate_existing=True)
    assert claimed.workflow_run_id == "run-1"
    assert claimed.workflow_node_id == "node-a"
    assert claimed.workflow_node_attempt == 1

    # 第二次走精确三列查询，仍返回同一条
    again = await find_existing_workflow_node_task(db_session, run_id="run-1", node_id="node-a")
    assert again is not None and again.id == legacy.id


@pytest.mark.asyncio
async def test_lookup_ignores_legacy_task_with_mismatched_params(
    db_session: AsyncSession,
) -> None:
    user = User(id="user-1", email="u@example.com", password_hash="hash")
    legacy = _task(
        task_id="legacy-2",
        status=TaskStatus.RUNNING.value,
        run_id=None,
        node_id=None,
        attempt=None,
    )
    db_session.add_all([
        user,
        legacy,
        TaskInput(
            task_id=legacy.id,
            params={"workflow_run_id": "run-9", "workflow_node_id": "node-a"},
            file_ids=[],
        ),
    ])
    await db_session.flush()

    found = await find_existing_workflow_node_task(db_session, run_id="run-1", node_id="node-a")
    assert found is None
