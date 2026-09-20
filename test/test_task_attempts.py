"""任务执行 attempt 提交门测试。"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import tasks as _task_models  # noqa: F401
from app.models.tasks import Task, TaskStatus
from app.tasks.attempts import commit_current_attempt


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
