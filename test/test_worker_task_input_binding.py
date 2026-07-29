"""Worker 任务执行时的输入绑定回归测试。"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import tools as _tools_models  # noqa: F401
from app.models import users as _users_models  # noqa: F401
from app.models.tasks import Task, TaskInput, TaskOutput, TaskStatus
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.worker import tasks as worker_tasks


def test_celery_sync_tasks_run_without_a_preexisting_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Celery worker 线程不应依赖隐式创建的 asyncio event loop。"""

    async def fake_execute(task_id: str, tool_version_id: str) -> dict[str, str]:
        return {"task_id": task_id, "tool_version_id": tool_version_id}

    async def fake_cleanup() -> int:
        return 3

    monkeypatch.setattr(worker_tasks, "_execute_tool_task_impl", fake_execute)
    monkeypatch.setattr(worker_tasks, "_cleanup_expired_files_impl", fake_cleanup)

    with ThreadPoolExecutor(max_workers=1) as executor:
        task_result = executor.submit(
            worker_tasks.execute_tool_task.run,
            "task-1",
            "version-1",
        ).result()
        cleanup_result = executor.submit(worker_tasks.cleanup_expired_files.run).result()

    assert task_result == {"task_id": "task-1", "tool_version_id": "version-1"}
    assert cleanup_result == {"deleted_count": 3}


@pytest_asyncio.fixture
async def db_session_factory():
    """创建隔离的异步数据库会话工厂。"""
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

    yield session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_execute_tool_task_impl_binds_task_input_before_executor(
    db_session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    """Worker 应在执行器运行前绑定 task.inputs，避免异步懒加载报错。"""

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(worker_tasks, "notify_task_status", noop)
    monkeypatch.setattr(worker_tasks, "notify_task_log", noop)
    monkeypatch.setattr(worker_tasks, "notify_task_progress", noop)
    monkeypatch.setattr(worker_tasks, "notify_task_complete", noop)
    monkeypatch.setattr(worker_tasks, "notify_task_error", noop)

    monkeypatch.setattr("app.database.session.async_session_factory", db_session_factory)

    async with db_session_factory() as session:
        user = User(
            email="worker@example.com",
            password_hash="hashed-password",
            display_name="Worker",
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        await session.flush()

        tool = Tool(
            owner_id=user.id,
            name="SSH Tool",
            slug="ssh-tool-binding-test",
            description="Worker binding regression test",
            category="generation",
            status=ToolStatus.PUBLISHED.value,
            is_public=True,
        )
        session.add(tool)
        await session.flush()

        version = ToolVersion(
            tool_id=tool.id,
            version="1.0.0",
            config={"type": "ssh_job"},
            is_active=True,
        )
        session.add(version)
        await session.flush()
        tool.current_version_id = version.id

        task = Task(
            user_id=user.id,
            tool_id=tool.id,
            tool_version_id=version.id,
            status=TaskStatus.PENDING.value,
            priority="normal",
            progress=0.0,
        )
        session.add(task)
        await session.flush()

        task_input = TaskInput(
            task_id=task.id,
            params={"params": {"foo": "bar"}},
            file_ids=[],
        )
        session.add(task_input)
        await session.commit()

        task_id = str(task.id)
        version_id = str(version.id)

    async def fake_execute(self):
        assert self.task.inputs is not None
        assert self.task.inputs.params == {"params": {"foo": "bar"}}
        return {"success": True, "message": "ok"}

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fake_execute)

    result = await worker_tasks._execute_tool_task_impl(task_id, version_id)

    assert result["success"] is True

    async with db_session_factory() as session:
        refreshed_task = (await session.execute(select(Task).where(Task.id == task_id))).scalar_one()
        task_output = (await session.execute(select(TaskOutput).where(TaskOutput.task_id == task_id))).scalar_one()

        assert refreshed_task.status == TaskStatus.SUCCESS.value
        assert task_output.result["message"] == "ok"
