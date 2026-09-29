"""任务执行 attempt 提交门测试。"""

from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import tasks as _task_models  # noqa: F401
from app.models.tasks import Task, TaskStatus
from app.common.time import utcnow
from app.config import settings
from app.worker import tasks as worker_tasks
from app.tasks.attempts import (
    commit_current_attempt,
    get_execution_control,
    is_task_cancellation_pending,
    mark_task_cancellation_timed_out,
)


@pytest_asyncio.fixture
async def db_session_factory():
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

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_stale_attempt_cannot_commit_terminal_state(db_session_factory) -> None:
    async with db_session_factory() as db:
        task = Task(
            user_id="user-1",
            tool_id="tool-1",
            tool_version_id="version-1",
            status=TaskStatus.RUNNING.value,
            progress=42.0,
            extra_data={"execution_attempt_id": "attempt-new"},
        )
        db.add(task)
        await db.commit()
        task_id = task.id

        task.status = TaskStatus.SUCCESS.value
        task.progress = 100.0
        committed = await commit_current_attempt(
            db,
            task=task,
            attempt_id="attempt-old",
            expected_status=TaskStatus.RUNNING,
        )

        assert committed is False

    async with db_session_factory() as db:
        stored = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one()
        assert stored.status == TaskStatus.RUNNING.value
        assert stored.progress == 42.0


@pytest.mark.asyncio
async def test_current_attempt_can_commit_terminal_state(db_session_factory) -> None:
    async with db_session_factory() as db:
        task = Task(
            user_id="user-1",
            tool_id="tool-1",
            tool_version_id="version-1",
            status=TaskStatus.RUNNING.value,
            progress=42.0,
            extra_data={"execution_attempt_id": "attempt-current"},
        )
        db.add(task)
        await db.commit()
        task_id = task.id

        task.status = TaskStatus.SUCCESS.value
        task.progress = 100.0
        committed = await commit_current_attempt(
            db,
            task=task,
            attempt_id="attempt-current",
            expected_status=TaskStatus.RUNNING,
        )

        assert committed is True

    async with db_session_factory() as db:
        stored = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one()
        assert stored.status == TaskStatus.SUCCESS.value
        assert stored.progress == 100.0


def test_cancellation_timeout_stays_retry_blocking() -> None:
    task = Task(
        extra_data={
            "execution_control": {
                "state": "cancel_requested",
                "attempt_id": "attempt-old",
                "requested_at": "2026-09-24T00:00:00",
            }
        }
    )

    mark_task_cancellation_timed_out(
        task,
        timed_out_at="2026-09-24T00:10:00",
        reason="worker_exit_not_confirmed",
    )

    control = get_execution_control(task)
    assert control["state"] == "cancel_timeout"
    assert control["manual_intervention_required"] is True
    assert control["timed_out_at"] == "2026-09-24T00:10:00"
    assert is_task_cancellation_pending(task) is True


@pytest.mark.asyncio
async def test_reaper_marks_stale_cancellation_without_releasing_reservation(
    db_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_at = utcnow() - timedelta(seconds=120)
    async with db_session_factory() as db:
        task = Task(
            user_id="user-1",
            tool_id="tool-1",
            tool_version_id="version-1",
            status=TaskStatus.CANCELED.value,
            extra_data={
                "execution_control": {
                    "state": "cancel_requested",
                    "attempt_id": "attempt-old",
                    "requested_at": requested_at.isoformat(),
                },
                "dispatch": {
                    "resource_reservation": {
                        "status": "running",
                        "lease_id": "lease-old",
                    }
                },
            },
        )
        db.add(task)
        await db.commit()
        task_id = task.id

    monkeypatch.setattr(
        "app.database.session.async_session_factory",
        db_session_factory,
    )
    monkeypatch.setattr(
        settings,
        "TASK_CANCELLATION_STALE_AFTER_SECONDS",
        60,
        raising=False,
    )
    monkeypatch.setattr(
        settings,
        "TASK_CANCELLATION_RECONCILE_BATCH_SIZE",
        10,
        raising=False,
    )

    assert await worker_tasks._reclaim_stale_cancellations_impl() == 1

    async with db_session_factory() as db:
        refreshed = await db.get(Task, task_id)
        control = refreshed.extra_data["execution_control"]
        reservation = refreshed.extra_data["dispatch"]["resource_reservation"]
        assert control["state"] == "cancel_timeout"
        assert control["manual_intervention_required"] is True
        assert reservation["status"] == "running"


@pytest.mark.asyncio
async def test_remote_cancel_reconciler_honors_next_retry_time(
    db_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = utcnow()
    async with db_session_factory() as db:
        stale = Task(
            user_id="user-1",
            tool_id="tool-1",
            tool_version_id="version-1",
            status=TaskStatus.CANCELED.value,
            extra_data={"remote_cancel_pending": True},
        )
        deferred = Task(
            user_id="user-1",
            tool_id="tool-1",
            tool_version_id="version-1",
            status=TaskStatus.CANCELED.value,
            extra_data={
                "remote_cancel_pending": True,
                "remote_cancel_next_retry_at": (
                    now + timedelta(minutes=5)
                ).isoformat(),
            },
        )
        db.add_all([stale, deferred])
        await db.commit()

    retried_ids: list[str] = []

    async def fake_retry(db, *, task):
        retried_ids.append(str(task.id))
        return True

    monkeypatch.setattr(
        "app.database.session.async_session_factory",
        db_session_factory,
    )
    monkeypatch.setattr(
        "app.tasks.cancellation.retry_remote_tool_cancellation",
        fake_retry,
    )
    monkeypatch.setattr(settings, "REMOTE_CANCEL_RETRY_BATCH_SIZE", 10, raising=False)

    assert await worker_tasks._reconcile_remote_cancellations_impl() == 1
    assert retried_ids == [str(stale.id)]
