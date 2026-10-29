"""Execution-hardening: blocked node termination and workflow run timeout."""

from __future__ import annotations

import sys
from datetime import timedelta
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

import app.models  # noqa: F401,E402  (register every table on Base.metadata)
from app.common.time import utcnow  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.models.users import User  # noqa: E402
from app.models.workflows import WorkflowRun  # noqa: E402
from app.services.workflow_cancellation import mark_workflow_run_canceled  # noqa: E402
from app.services.workflow_reconciliation import (  # noqa: E402
    reconcile_waiting_workflow_runs,
)
from app.services.workflow_scheduler import start_ready_workflow_nodes  # noqa: E402
from app.services.workflow_skip import mark_unreachable_nodes_skipped  # noqa: E402


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


async def _create_run(
    db: AsyncSession,
    *,
    node_states: dict,
    execution_order: list[str],
    status: str = "waiting_task",
    created_at=None,
) -> tuple[User, WorkflowRun]:
    owner = User(email="exec-hardening@example.com", password_hash="x")
    db.add(owner)
    await db.flush()
    run = WorkflowRun(
        owner_id=owner.id,
        workflow_definition_id="wf-exec-hardening",
        name="exec-hardening run",
        status=status,
        definition={"nodes": [{"id": nid} for nid in execution_order], "edges": []},
        execution_order=execution_order,
        node_states=node_states,
    )
    if created_at is not None:
        run.created_at = created_at
    db.add(run)
    await db.commit()
    return owner, run


async def _noop_schedule(**kwargs):  # pragma: no cover - must never be called
    raise AssertionError("schedule_task_fn should not be called for terminal nodes")


@pytest.mark.asyncio
async def test_blocked_node_converges_run_to_failure(db_session: AsyncSession) -> None:
    owner, run = await _create_run(
        db_session,
        node_states={
            "prepare": {"status": "blocked", "blocked_reason": "missing prepared PDB"},
            "done": {"status": "success"},
        },
        execution_order=["prepare", "done"],
    )

    scheduled = await start_ready_workflow_nodes(
        db_session,
        current_user=owner,
        run=run,
        schedule_task_fn=_noop_schedule,
    )

    assert scheduled == 0
    assert run.status == "failure"
    assert run.finished_at is not None
    assert "prepare" in (run.error_message or "")


@pytest.mark.asyncio
async def test_run_without_blocked_converges_to_success(db_session: AsyncSession) -> None:
    owner, run = await _create_run(
        db_session,
        node_states={
            "a": {"status": "success"},
            "b": {"status": "skipped"},
        },
        execution_order=["a", "b"],
    )

    await start_ready_workflow_nodes(
        db_session,
        current_user=owner,
        run=run,
        schedule_task_fn=_noop_schedule,
    )

    assert run.status == "success"
    assert run.error_message is None


@pytest.mark.asyncio
async def test_reconcile_marks_timed_out_run_as_failure(
    db_session: AsyncSession,
) -> None:
    # Default threshold is 12h; make the run 13h old.
    _, run = await _create_run(
        db_session,
        node_states={"a": {"status": "running"}},
        execution_order=["a"],
        created_at=utcnow() - timedelta(hours=13),
    )

    processed = await reconcile_waiting_workflow_runs(
        db_session,
        batch_size=10,
        schedule_task_fn=_noop_schedule,
    )

    assert processed == 1
    assert run.status == "failure"
    assert run.finished_at is not None
    assert "timed out" in (run.error_message or "")
    assert "43200" in (run.error_message or "")


@pytest.mark.asyncio
async def test_reconcile_leaves_fresh_run_untouched(db_session: AsyncSession) -> None:
    _, run = await _create_run(
        db_session,
        node_states={"a": {"status": "running"}},
        execution_order=["a"],
        created_at=utcnow() - timedelta(hours=1),
    )

    processed = await reconcile_waiting_workflow_runs(
        db_session,
        batch_size=10,
        schedule_task_fn=_noop_schedule,
    )

    assert processed == 1
    assert run.status == "waiting_task"
    assert run.error_message is None
    assert run.finished_at is None


def test_cancel_leaves_blocked_node_untouched() -> None:
    run = SimpleNamespace(
        status="waiting_task",
        node_states={
            "blocked_node": {"status": "blocked", "blocked_reason": "no input"},
            "running_node": {"status": "running", "task_id": "task-running"},
        },
        finished_at=None,
        error_message=None,
    )

    task_ids = mark_workflow_run_canceled(run, finished_at="2026-10-29T00:00:00")

    assert task_ids == ["task-running"]
    assert run.status == "canceled"
    assert run.node_states["blocked_node"]["status"] == "blocked"
    assert run.node_states["running_node"]["status"] == "canceled"


def test_skip_propagation_does_not_override_blocked_node() -> None:
    node_states = {"blocked_node": {"status": "blocked", "blocked_reason": "no input"}}

    mark_unreachable_nodes_skipped(node_states, "blocked_node", "unreachable branch")

    assert node_states["blocked_node"]["status"] == "blocked"
