"""Worker 任务执行时的输入绑定回归测试。"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

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
from app.config import settings as config_settings
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import tools as _tools_models  # noqa: F401
from app.models import users as _users_models  # noqa: F401
from app.models.tasks import Task, TaskInput, TaskOutput, TaskStatus
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.tasks.executors.errors import GPUAllocationFailed, ResourceAdmissionFailed
from app.tasks.queue_manager import TaskQueueManager
from app.tasks.state_machine import TaskStateMachine
from app.worker import tasks as worker_tasks


def test_celery_registers_stale_gpu_lease_maintenance_task() -> None:
    """定时维护任务应注册到 Celery 任务路由。"""
    assert worker_tasks.reclaim_stale_gpu_leases.name == (
        "app.worker.tasks.reclaim_stale_gpu_leases"
    )
    assert worker_tasks.reconcile_execution_records.name == (
        "app.worker.tasks.reconcile_execution_records"
    )
    assert worker_tasks.reclaim_stale_resource_reservations.name == (
        "app.worker.tasks.reclaim_stale_resource_reservations"
    )
    assert worker_tasks.reclaim_stale_cancellations.name == (
        "app.worker.tasks.reclaim_stale_cancellations"
    )


def test_gpu_retry_delay_uses_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GPU 重试等待时间应按重试次数指数增长并受上限约束。"""
    monkeypatch.setattr(
        config_settings,
        "GPU_RETRY_INITIAL_BACKOFF_SECONDS",
        30,
        raising=False,
    )
    monkeypatch.setattr(
        config_settings,
        "GPU_RETRY_MAX_BACKOFF_SECONDS",
        90,
        raising=False,
    )

    assert worker_tasks._gpu_retry_delay_seconds(
        SimpleNamespace(extra_data={"resource_retry_count": 1})
    ) == 30
    assert worker_tasks._gpu_retry_delay_seconds(
        SimpleNamespace(extra_data={"resource_retry_count": 2})
    ) == 60
    assert worker_tasks._gpu_retry_delay_seconds(
        SimpleNamespace(extra_data={"resource_retry_count": 4})
    ) == 90


def test_celery_sync_tasks_run_without_a_preexisting_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Celery worker 线程不应依赖隐式创建的 asyncio event loop。"""

    async def fake_execute(task_id: str, tool_version_id: str) -> dict[str, str]:
        return {"task_id": task_id, "tool_version_id": tool_version_id}

    async def fake_cleanup() -> int:
        return 3

    async def fake_reclaim() -> int:
        return 2

    async def fake_reclaim_reservations() -> int:
        return 5

    async def fake_reclaim_cancellations() -> int:
        return 6

    async def fake_reconcile() -> int:
        return 4

    monkeypatch.setattr(worker_tasks, "_execute_tool_task_impl", fake_execute)
    monkeypatch.setattr(worker_tasks, "_cleanup_expired_files_impl", fake_cleanup)
    monkeypatch.setattr(worker_tasks, "_reclaim_stale_gpu_leases_impl", fake_reclaim)
    monkeypatch.setattr(
        worker_tasks,
        "_reclaim_stale_resource_reservations_impl",
        fake_reclaim_reservations,
    )
    monkeypatch.setattr(
        worker_tasks,
        "_reclaim_stale_cancellations_impl",
        fake_reclaim_cancellations,
    )
    monkeypatch.setattr(
        worker_tasks,
        "_reconcile_execution_records_impl",
        fake_reconcile,
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        task_result = executor.submit(
            worker_tasks.execute_tool_task.run,
            "task-1",
            "version-1",
        ).result()
        cleanup_result = executor.submit(worker_tasks.cleanup_expired_files.run).result()
        reclaim_result = executor.submit(
            worker_tasks.reclaim_stale_gpu_leases.run
        ).result()
        reservation_reclaim_result = executor.submit(
            worker_tasks.reclaim_stale_resource_reservations.run
        ).result()
        cancellation_reclaim_result = executor.submit(
            worker_tasks.reclaim_stale_cancellations.run
        ).result()
        reconcile_result = executor.submit(
            worker_tasks.reconcile_execution_records.run
        ).result()

    assert task_result == {"task_id": "task-1", "tool_version_id": "version-1"}
    assert cleanup_result == {"deleted_count": 3}
    assert reclaim_result == {"reclaimed_count": 2}
    assert reservation_reclaim_result == {"reclaimed_count": 5}
    assert cancellation_reclaim_result == {"timed_out_count": 6}
    assert reconcile_result == {"reconciled_count": 4}


def test_celery_task_does_not_retry_after_platform_execution_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """平台执行器已持久化失败后，Celery 不应再次创建第二套重试。"""
    async def fail_execute(task_id: str, tool_version_id: str) -> None:
        raise RuntimeError("platform failure already recorded")

    def unexpected_retry(*args, **kwargs):
        raise AssertionError("平台任务失败不应再次触发 Celery retry")

    monkeypatch.setattr(worker_tasks, "_execute_tool_task_impl", fail_execute)
    monkeypatch.setattr(worker_tasks.execute_tool_task, "retry", unexpected_retry)

    with pytest.raises(RuntimeError, match="platform failure already recorded"):
        worker_tasks.execute_tool_task.run("task-1", "version-1")


@pytest.mark.asyncio
async def test_finish_execution_record_uses_independent_session(
    monkeypatch: pytest.MonkeyPatch,
):
    """执行记录终态写回不能污染 Worker 的任务事务。"""

    record_session = object()
    received_sessions: list[object] = []

    class SessionContext:
        async def __aenter__(self):
            return record_session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    async def fake_finish(db, **kwargs):
        received_sessions.append(db)

    monkeypatch.setattr(
        "app.execution.records.finish_task_execution_record",
        fake_finish,
    )
    monkeypatch.setattr(
        "app.database.session.async_session_factory",
        lambda: SessionContext(),
    )

    from app.execution.records import finish_task_execution_record_best_effort

    await finish_task_execution_record_best_effort(
        task=SimpleNamespace(
            id="task-1",
            extra_data={"execution_record_id": "record-1"},
        ),
        status="succeeded",
    )

    assert received_sessions == [record_session]


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


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["start", "commit"])
async def test_execute_tool_task_impl_continues_when_execution_record_store_fails(
    db_session_factory,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
):
    """ExecutionRecord 写入异常不应阻断实际工具执行。"""

    async def noop(*args, **kwargs):
        return None

    for name in (
        "notify_task_status",
        "notify_task_log",
        "notify_task_progress",
        "notify_task_complete",
        "notify_task_error",
    ):
        monkeypatch.setattr(worker_tasks, name, noop)

    monkeypatch.setattr("app.database.session.async_session_factory", db_session_factory)

    async with db_session_factory() as session:
        user = User(
            email="execution-record-store@example.com",
            password_hash="hashed-password",
            display_name="Execution Record Store",
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        await session.flush()

        tool = Tool(
            owner_id=user.id,
            name="Execution Record Store Tool",
            slug="execution-record-store-tool",
            description="Execution record store failure regression test",
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

        task = Task(
            user_id=user.id,
            tool_id=tool.id,
            tool_version_id=version.id,
            status=TaskStatus.PENDING.value,
            priority="normal",
            progress=0.0,
            extra_data={"project_id": "project-1"},
        )
        session.add(task)
        await session.flush()
        session.add(TaskInput(task_id=task.id, params={}, file_ids=[]))
        await session.commit()
        task_id = str(task.id)
        version_id = str(version.id)

    async def fake_execute(self):
        return {"success": True, "message": "tool completed"}

    if failure_stage == "start":
        async def fail_to_start_record(*args, **kwargs):
            raise RuntimeError("execution record store unavailable")

        monkeypatch.setattr(
            "app.execution.records.start_task_execution_record",
            fail_to_start_record,
        )
    else:
        async def fake_start_record(db, *, task, **kwargs):
            task.extra_data = {
                **(task.extra_data or {}),
                "execution_record_id": "record-1",
            }
            return object()

        original_commit = worker_tasks.commit_current_attempt
        commit_calls = 0

        async def fail_to_commit_record(db, **kwargs):
            nonlocal commit_calls
            commit_calls += 1
            if commit_calls == 2:
                raise RuntimeError("execution record commit unavailable")
            return await original_commit(db, **kwargs)

        monkeypatch.setattr(
            "app.execution.records.start_task_execution_record",
            fake_start_record,
        )
        monkeypatch.setattr(
            worker_tasks,
            "commit_current_attempt",
            fail_to_commit_record,
        )

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fake_execute)

    result = await worker_tasks._execute_tool_task_impl(task_id, version_id)

    assert result["success"] is True

    async with db_session_factory() as session:
        refreshed_task = (
            await session.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert refreshed_task.status == TaskStatus.SUCCESS.value


@pytest.mark.asyncio
async def test_execute_tool_task_impl_keeps_success_when_record_finish_fails(
    db_session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    """ExecutionRecord 终态写回失败不应把已成功工具改成失败。"""

    async def noop(*args, **kwargs):
        return None

    for name in (
        "notify_task_status",
        "notify_task_log",
        "notify_task_progress",
        "notify_task_complete",
        "notify_task_error",
    ):
        monkeypatch.setattr(worker_tasks, name, noop)

    monkeypatch.setattr("app.database.session.async_session_factory", db_session_factory)

    async with db_session_factory() as session:
        user = User(
            email="execution-record-finish@example.com",
            password_hash="hashed-password",
            display_name="Execution Record Finish",
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        await session.flush()

        tool = Tool(
            owner_id=user.id,
            name="Execution Record Finish Tool",
            slug="execution-record-finish-tool",
            description="Execution record finish failure regression test",
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

        task = Task(
            user_id=user.id,
            tool_id=tool.id,
            tool_version_id=version.id,
            status=TaskStatus.PENDING.value,
            priority="normal",
            progress=0.0,
            extra_data={"project_id": "project-1"},
        )
        session.add(task)
        await session.flush()
        session.add(TaskInput(task_id=task.id, params={}, file_ids=[]))
        await session.commit()
        task_id = str(task.id)
        version_id = str(version.id)

    async def fake_start(db, *, task, **kwargs):
        task.extra_data = {
            **(task.extra_data or {}),
            "execution_record_id": "record-1",
        }
        return object()

    async def fail_to_finish(*args, **kwargs):
        raise RuntimeError("execution record finish unavailable")

    async def fake_execute(self):
        return {"success": True, "message": "tool completed"}

    monkeypatch.setattr(
        "app.execution.records.start_task_execution_record",
        fake_start,
    )
    monkeypatch.setattr(
        "app.execution.records.finish_task_execution_record",
        fail_to_finish,
    )
    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fake_execute)

    result = await worker_tasks._execute_tool_task_impl(task_id, version_id)

    assert result["success"] is True
    async with db_session_factory() as session:
        refreshed_task = (
            await session.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert refreshed_task.status == TaskStatus.SUCCESS.value


@pytest.mark.asyncio
async def test_execute_tool_task_impl_persists_execution_record_pointer_before_failure(
    db_session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    """执行失败回滚后，ExecutionRecord 指针仍应可用于写回失败状态。"""

    async def noop(*args, **kwargs):
        return None

    for name in (
        "notify_task_status",
        "notify_task_log",
        "notify_task_progress",
        "notify_task_complete",
        "notify_task_error",
    ):
        monkeypatch.setattr(worker_tasks, name, noop)

    monkeypatch.setattr("app.database.session.async_session_factory", db_session_factory)

    async with db_session_factory() as session:
        user = User(
            email="execution-record-failure@example.com",
            password_hash="hashed-password",
            display_name="Execution Record Failure",
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        await session.flush()

        tool = Tool(
            owner_id=user.id,
            name="Execution Record Tool",
            slug="execution-record-failure-tool",
            description="Execution record failure regression test",
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

        task = Task(
            user_id=user.id,
            tool_id=tool.id,
            tool_version_id=version.id,
            status=TaskStatus.PENDING.value,
            priority="normal",
            progress=0.0,
            extra_data={"project_id": "project-1"},
        )
        session.add(task)
        await session.flush()
        session.add(TaskInput(task_id=task.id, params={}, file_ids=[]))
        await session.commit()
        task_id = str(task.id)
        version_id = str(version.id)

    finished: list[tuple[str | None, str, str | None]] = []

    async def fake_start(db, *, task, **kwargs):
        task.extra_data = {
            **(task.extra_data or {}),
            "execution_record_id": "record-1",
        }
        return object()

    async def fake_finish(*, task, status, external_id=None, **kwargs):
        finished.append(
            (task.extra_data.get("execution_record_id"), status, external_id)
        )

    monkeypatch.setattr(
        "app.execution.records.start_task_execution_record",
        fake_start,
    )
    monkeypatch.setattr(
        worker_tasks,
        "finish_task_execution_record_best_effort",
        fake_finish,
    )

    async def fail_execute(self):
        self.task.extra_data = {
            **(self.task.extra_data or {}),
            "remote_run_id": "run-1",
        }
        raise RuntimeError("execution failed")

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fail_execute)

    with pytest.raises(RuntimeError, match="execution failed"):
        await worker_tasks._execute_tool_task_impl(task_id, version_id)

    assert finished == [("record-1", "failed", "run-1")]


@pytest.mark.asyncio
async def test_execute_tool_task_impl_requeues_gpu_shortage_before_failure(
    db_session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    """GPU 暂时不足且未达上限时，worker 应保留任务并重新调度。"""

    async def noop(*args, **kwargs):
        return None

    for name in (
        "notify_task_status",
        "notify_task_log",
        "notify_task_progress",
        "notify_task_complete",
        "notify_task_error",
    ):
        monkeypatch.setattr(worker_tasks, name, noop)

    monkeypatch.setattr("app.database.session.async_session_factory", db_session_factory)
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    scheduled: list[tuple[str, str, int]] = []
    monkeypatch.setattr(
        "app.tasks.direct_runner.direct_task_runner",
        type(
            "DeferredRunner",
            (),
            {
                "schedule_task_after_current": lambda self, task_id, tool_version_id, delay_seconds=0, **kwargs: scheduled.append(
                    (task_id, tool_version_id, delay_seconds)
                )
            },
        )(),
    )

    async with db_session_factory() as session:
        user = User(
            email="gpu-worker@example.com",
            password_hash="hashed-password",
            display_name="GPU Worker",
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        await session.flush()

        tool = Tool(
            owner_id=user.id,
            name="GPU Tool",
            slug="gpu-worker-requeue-test",
            description="GPU requeue regression test",
            category="generation",
            status=ToolStatus.PUBLISHED.value,
            is_public=True,
            gpu_required=True,
            gpu_memory_mb=4096,
        )
        session.add(tool)
        await session.flush()

        version = ToolVersion(
            tool_id=tool.id,
            version="1.0.0",
            config={"type": "docker_image", "image": "test:latest", "gpu_required": True},
            is_active=True,
        )
        session.add(version)
        await session.flush()
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
        session.add(TaskInput(task_id=task.id, params={}, file_ids=[]))
        await session.commit()
        task_id = str(task.id)
        version_id = str(version.id)

    async def fail_for_gpu_shortage(self):
        raise GPUAllocationFailed("No GPU", wait_position=2)

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fail_for_gpu_shortage)

    result = await worker_tasks._execute_tool_task_impl(task_id, version_id)

    assert result["status"] == TaskStatus.QUEUED.value
    assert scheduled == [(task_id, version_id, 30)]

    async with db_session_factory() as session:
        refreshed_task = (await session.execute(select(Task).where(Task.id == task_id))).scalar_one()
        assert refreshed_task.status == TaskStatus.QUEUED.value
        # 用户重试额度必须不被基础设施重排消耗
        assert (refreshed_task.retry_count or 0) == 0
        assert refreshed_task.error_message is None
        assert refreshed_task.extra_data["resource_wait_reason"] == "gpu_unavailable"
        assert refreshed_task.extra_data["resource_retry_count"] == 1
        assert refreshed_task.extra_data["resource_retry_next_at"]


@pytest.mark.asyncio
async def test_execute_tool_task_impl_requeues_worker_capability_wait(
    db_session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    """Worker capability 不匹配时，应进入资源等待而不是直接失败。"""

    async def noop(*args, **kwargs):
        return None

    for name in (
        "notify_task_status",
        "notify_task_log",
        "notify_task_progress",
        "notify_task_complete",
        "notify_task_error",
    ):
        monkeypatch.setattr(worker_tasks, name, noop)

    monkeypatch.setattr("app.database.session.async_session_factory", db_session_factory)
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    scheduled: list[tuple[str, str, int]] = []
    monkeypatch.setattr(
        "app.tasks.direct_runner.direct_task_runner",
        type(
            "DeferredRunner",
            (),
            {
                "schedule_task_after_current": lambda self, task_id, tool_version_id, delay_seconds=0, **kwargs: scheduled.append(
                    (task_id, tool_version_id, delay_seconds)
                )
            },
        )(),
    )

    async with db_session_factory() as session:
        user = User(
            email="capability-worker@example.com",
            password_hash="hashed-password",
            display_name="Capability Worker",
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        await session.flush()

        tool = Tool(
            owner_id=user.id,
            name="Capability Tool",
            slug="capability-worker-requeue-test",
            description="Worker capability requeue regression test",
            category="generation",
            status=ToolStatus.PUBLISHED.value,
            is_public=True,
        )
        session.add(tool)
        await session.flush()

        version = ToolVersion(
            tool_id=tool.id,
            version="1.0.0",
            config={
                "type": "docker_image",
                "image": "test:latest",
                "resource_profile": {"tier": "heavy", "cpu": 8},
            },
            is_active=True,
        )
        session.add(version)
        await session.flush()
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
        session.add(TaskInput(task_id=task.id, params={}, file_ids=[]))
        await session.commit()
        task_id = str(task.id)
        version_id = str(version.id)

    async def fail_for_capability_wait(self):
        raise ResourceAdmissionFailed(
            "资源准入失败: no_capable_worker",
            reason="no_capable_worker",
        )

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fail_for_capability_wait)

    result = await worker_tasks._execute_tool_task_impl(task_id, version_id)

    assert result["status"] == TaskStatus.QUEUED.value
    assert scheduled == [(task_id, version_id, 30)]

    async with db_session_factory() as session:
        refreshed_task = (
            await session.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert refreshed_task.status == TaskStatus.QUEUED.value
        assert (refreshed_task.retry_count or 0) == 0
        assert refreshed_task.error_message is None
        assert refreshed_task.extra_data["resource_wait_reason"] == "worker_capability_unavailable"
        assert refreshed_task.extra_data["resource_wait_code"] == "no_capable_worker"
        assert refreshed_task.extra_data["resource_wait_category"] == "resource"
        assert refreshed_task.extra_data["resource_retry_count"] == 1
        assert refreshed_task.extra_data["resource_retry_next_at"]


@pytest.mark.asyncio
async def test_execute_tool_task_impl_requeues_gpu_shortage_through_celery(
    db_session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    """Celery 重入队应复用资源快照并保存新的调度信息。"""

    async def noop(*args, **kwargs):
        return None

    for name in (
        "notify_task_status",
        "notify_task_log",
        "notify_task_progress",
        "notify_task_complete",
        "notify_task_error",
    ):
        monkeypatch.setattr(worker_tasks, name, noop)

    monkeypatch.setattr("app.database.session.async_session_factory", db_session_factory)
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr(config_settings, "CELERY_BROKER_URL", "redis://test", raising=False)
    queued: list[tuple[str, str, str, int]] = []

    def fake_enqueue(
        cls,
        task_id: str,
        tool_version_id: str,
        queue: str,
        countdown: int = 0,
    ):
        queued.append((task_id, tool_version_id, queue, countdown))
        return SimpleNamespace(id="celery-gpu-retry")

    monkeypatch.setattr(TaskQueueManager, "enqueue_task", classmethod(fake_enqueue))

    async with db_session_factory() as session:
        user = User(
            email="gpu-celery@example.com",
            password_hash="hashed-password",
            display_name="GPU Celery",
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        await session.flush()

        tool = Tool(
            owner_id=user.id,
            name="GPU Celery Tool",
            slug="gpu-celery-requeue-test",
            description="GPU Celery requeue regression test",
            category="generation",
            status=ToolStatus.PUBLISHED.value,
            is_public=True,
        )
        session.add(tool)
        await session.flush()

        version = ToolVersion(
            tool_id=tool.id,
            version="1.0.0",
            config={"type": "docker_image", "image": "test:latest"},
            is_active=True,
        )
        session.add(version)
        await session.flush()

        task = Task(
            user_id=user.id,
            tool_id=tool.id,
            tool_version_id=version.id,
            status=TaskStatus.PENDING.value,
            priority="normal",
            progress=0.0,
            extra_data={
                "resource_snapshot": {
                    "gpu_required": True,
                    "gpu_memory_mb": 4096,
                }
            },
        )
        session.add(task)
        await session.flush()
        session.add(TaskInput(task_id=task.id, params={}, file_ids=[]))
        await session.commit()
        task_id = str(task.id)
        version_id = str(version.id)

    async def fail_for_gpu_shortage(self):
        raise GPUAllocationFailed("No GPU", wait_position=1)

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fail_for_gpu_shortage)

    result = await worker_tasks._execute_tool_task_impl(task_id, version_id)

    assert result["status"] == TaskStatus.QUEUED.value
    assert queued == [(task_id, version_id, "gpu_queue", 30)]

    async with db_session_factory() as session:
        refreshed_task = (
            await session.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert refreshed_task.status == TaskStatus.QUEUED.value
        assert refreshed_task.celery_task_id == "celery-gpu-retry"
        assert refreshed_task.extra_data["dispatch"] == {
            "mode": "celery",
            "queue": "gpu_queue",
            "queue_priority": 5,
        }
        assert refreshed_task.extra_data["resource_wait_reason"] == "gpu_unavailable"
        assert refreshed_task.extra_data["resource_retry_count"] == 1
        assert refreshed_task.extra_data["resource_retry_next_at"]


@pytest.mark.asyncio
async def test_execute_tool_task_impl_does_not_overwrite_user_cancellation(
    db_session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    """执行返回时若用户已取消，worker 不得把任务写回成功。"""

    async def noop(*args, **kwargs):
        return None

    for name in (
        "notify_task_status",
        "notify_task_log",
        "notify_task_progress",
        "notify_task_complete",
        "notify_task_error",
    ):
        monkeypatch.setattr(worker_tasks, name, noop)

    monkeypatch.setattr("app.database.session.async_session_factory", db_session_factory)

    async with db_session_factory() as session:
        user = User(
            email="cancel-race@example.com",
            password_hash="hashed-password",
            display_name="Cancel Race",
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        await session.flush()

        tool = Tool(
            owner_id=user.id,
            name="Cancel Race Tool",
            slug="cancel-race-tool",
            description="Cancellation race regression test",
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
        session.add(TaskInput(task_id=task.id, params={}, file_ids=[]))
        await session.commit()
        task_id = str(task.id)
        version_id = str(version.id)

    async def finish_after_external_cancel(self):
        async with db_session_factory() as cancel_session:
            canceled_task = await cancel_session.get(Task, task_id)
            assert canceled_task is not None
            TaskStateMachine.cancel(canceled_task)
            await cancel_session.commit()
        return {"success": True, "message": "late result"}

    monkeypatch.setattr(
        "app.tasks.executor.TaskExecutor.execute",
        finish_after_external_cancel,
    )

    result = await worker_tasks._execute_tool_task_impl(task_id, version_id)

    assert result["status"] == TaskStatus.CANCELED.value

    async with db_session_factory() as session:
        refreshed_task = (
            await session.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert refreshed_task.status == TaskStatus.CANCELED.value
        assert (
            await session.execute(select(TaskOutput).where(TaskOutput.task_id == task_id))
        ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_execute_tool_task_impl_skips_already_canceled_queued_task(
    db_session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    """撤销竞态下，已取消的队列消息不得重新启动任务。"""

    monkeypatch.setattr("app.database.session.async_session_factory", db_session_factory)

    async with db_session_factory() as session:
        task = Task(
            user_id="user-1",
            tool_id="tool-1",
            tool_version_id="version-1",
            status=TaskStatus.CANCELED.value,
            priority="normal",
            progress=0.0,
        )
        session.add(task)
        await session.commit()
        task_id = str(task.id)

    result = await worker_tasks._execute_tool_task_impl(task_id, "version-1")

    assert result["status"] == TaskStatus.CANCELED.value


@pytest.mark.asyncio
async def test_execute_tool_task_impl_ignores_stale_execution_attempt(
    db_session_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    """重试后到达的旧消息不得再次启动执行器。"""

    monkeypatch.setattr("app.database.session.async_session_factory", db_session_factory)

    async with db_session_factory() as session:
        task = Task(
            user_id="user-1",
            tool_id="tool-1",
            tool_version_id="version-1",
            status=TaskStatus.PENDING.value,
            priority="normal",
            progress=0.0,
            extra_data={"execution_attempt_id": "attempt-new"},
        )
        session.add(task)
        await session.commit()
        task_id = str(task.id)

    async def unexpected_execute(self):
        raise AssertionError("过期 attempt 不应进入执行器")

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", unexpected_execute)

    result = await worker_tasks._execute_tool_task_impl(
        task_id,
        "version-1",
        "attempt-old",
    )

    assert result["stale"] is True
    assert result["status"] == TaskStatus.PENDING.value
