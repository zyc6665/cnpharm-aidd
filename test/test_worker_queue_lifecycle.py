"""纯后端 Worker 队列与动态资源租约交接测试。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cache.memory import MemoryCacheBackend
from app.api.v1.tasks import delete_task
from app.config import settings
from app.models.tasks import TaskStatus
from app.tasks.cancellation import cancel_platform_task
from app.tasks.attempts import is_task_cancellation_pending
from app.tasks.executors.factory import TaskExecutor
from app.tasks.resource_admission import WorkerCapability
from app.tasks.resource_lease import (
    WorkerResourceLeaseManager,
    release_task_resource_reservation,
)
from app.tasks.resource_profile import (
    build_task_resource_snapshot,
    resource_request_from_snapshot,
)
from app.tasks.queue_manager import TaskQueueManager
from app.tasks.service import dispatch_tool_task
from app.common.exceptions import ConflictException


def _tool_version() -> SimpleNamespace:
    return SimpleNamespace(
        id="version-worker-queue",
        config={
            "type": "docker_image",
            "resource_profile": {
                "tier": "heavy",
                "cpu": 4,
                "memory_gb": 8,
                "parallelism": 1,
            },
        },
    )


def _task() -> SimpleNamespace:
    snapshot = build_task_resource_snapshot(_tool_version().config)
    return SimpleNamespace(
        id="task-worker-queue",
        user_id="user-worker-queue",
        project_id="project-worker-queue",
        priority="normal",
        status="PENDING",
        created_at=None,
        extra_data={"resource_snapshot": snapshot},
        celery_task_id=None,
    )


@pytest.mark.asyncio
async def test_dispatch_reservation_is_claimed_by_worker_executor(monkeypatch):
    cache = MemoryCacheBackend()
    worker = WorkerCapability(
        worker_id="cpu-worker-queue",
        queue="cpu-worker-queue",
        executor_types=("docker_image",),
        tiers=("heavy",),
        cpu_capacity=8,
        memory_capacity_gb=16,
        parallelism=2,
    )

    from app.tasks.worker_capability_registry import WorkerCapabilityRegistry

    await WorkerCapabilityRegistry(cache=cache, ttl_seconds=60).register(worker)
    monkeypatch.setattr("app.cache.get_cache", lambda: cache)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ADMISSION_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ROUTING_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_RESERVATION_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "RESOURCE_DISPATCH_RESERVATION_TTL_SECONDS", 60, raising=False)
    monkeypatch.setattr(settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: False)
    monkeypatch.setattr(
        TaskQueueManager,
        "enqueue_task",
        classmethod(lambda cls, **kwargs: SimpleNamespace(id="celery-worker-queue")),
    )

    task = _task()
    db = SimpleNamespace(commit=AsyncMock())
    tool_version = _tool_version()

    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=tool_version,
        user_role="user",
    )

    reservation = task.extra_data["dispatch"]["resource_reservation"]
    assert reservation["status"] == "reserved"
    manager = WorkerResourceLeaseManager(cache=cache)
    assert await manager.current_lease_phase_counts(worker.worker_id) == {
        "reserved": 1,
        "running": 0,
        "unknown": 0,
    }

    executor = TaskExecutor(
        task,
        tool_version,
        cache_client=cache,
        worker_capability=worker,
    )
    await executor._acquire_resources()

    assert task.extra_data["dispatch"]["resource_reservation"]["status"] == "claimed"
    assert await manager.current_lease_phase_counts(worker.worker_id) == {
        "reserved": 0,
        "running": 1,
        "unknown": 0,
    }

    await executor._release_resource_lease()
    assert await manager.current_usage(worker.worker_id) == {
        "cpu": 0.0,
        "memory_gb": 0.0,
        "parallelism": 0,
    }

    await executor._release_resource_lease()
    assert await manager.current_usage(worker.worker_id) == {
        "cpu": 0.0,
        "memory_gb": 0.0,
        "parallelism": 0,
    }


@pytest.mark.asyncio
async def test_running_worker_lease_heartbeat_refreshes_until_release(monkeypatch):
    cache = MemoryCacheBackend()
    worker = WorkerCapability(
        worker_id="cpu-worker-heartbeat",
        queue="cpu-worker-heartbeat",
        executor_types=("docker_image",),
        tiers=("heavy",),
        cpu_capacity=8,
        memory_capacity_gb=16,
        parallelism=2,
    )
    task = _task()
    task.id = "task-worker-heartbeat"
    executor = TaskExecutor(
        task,
        _tool_version(),
        cache_client=cache,
        worker_capability=worker,
    )
    heartbeat_calls = 0
    original_heartbeat = WorkerResourceLeaseManager.heartbeat

    async def tracked_heartbeat(self, *, worker_id, lease_id, ttl_seconds):
        nonlocal heartbeat_calls
        heartbeat_calls += 1
        return await original_heartbeat(
            self,
            worker_id=worker_id,
            lease_id=lease_id,
            ttl_seconds=ttl_seconds,
        )

    monkeypatch.setattr(
        WorkerResourceLeaseManager,
        "HEARTBEAT_INTERVAL_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        WorkerResourceLeaseManager,
        "heartbeat",
        tracked_heartbeat,
    )

    await executor._acquire_resources()
    await asyncio.sleep(0.08)

    assert heartbeat_calls >= 1
    await executor._release_resource_lease()
    assert await WorkerResourceLeaseManager(cache=cache).current_usage(
        worker.worker_id,
    ) == {
        "cpu": 0.0,
        "memory_gb": 0.0,
        "parallelism": 0,
    }


@pytest.mark.asyncio
async def test_cancelled_running_lease_cleanup_is_idempotent():
    cache = MemoryCacheBackend()
    worker = WorkerCapability(
        worker_id="cpu-worker-cancel",
        queue="cpu-worker-cancel",
        executor_types=("docker_image",),
        tiers=("heavy",),
        cpu_capacity=8,
        memory_capacity_gb=16,
        parallelism=2,
    )
    task = _task()
    task.id = "task-worker-cancel"
    task.extra_data["execution_attempt_id"] = "attempt-1"
    task.extra_data["dispatch"] = {
        "resource_reservation": {
            "worker_id": worker.worker_id,
            "lease_id": f"{task.id}:attempt-1",
            "ttl_seconds": 60,
            "status": "reserved",
        }
    }
    request = resource_request_from_snapshot(
        _tool_version().config,
        task.extra_data["resource_snapshot"],
    )
    manager = WorkerResourceLeaseManager(cache=cache)
    assert (
        await manager.acquire(
            capability=worker,
            request=request,
            lease_id=f"{task.id}:attempt-1",
            ttl_seconds=60,
            lease_phase="reserved",
        )
    ).acquired is True

    executor = TaskExecutor(
        task,
        _tool_version(),
        cache_client=cache,
        worker_capability=worker,
    )
    await executor._acquire_resources()
    assert await manager.current_usage(worker.worker_id) == {
        "cpu": 4.0,
        "memory_gb": 8.0,
        "parallelism": 1,
    }

    assert await release_task_resource_reservation(
        task,
        reason="task_canceled_during_execution",
        attempt_id="attempt-1",
        cache=cache,
    ) is True
    assert task.extra_data["dispatch"]["resource_reservation"]["status"] == "released"
    assert await manager.current_usage(worker.worker_id) == {
        "cpu": 0.0,
        "memory_gb": 0.0,
        "parallelism": 0,
    }


@pytest.mark.asyncio
async def test_running_task_cancel_defers_resource_lease_release(monkeypatch):
    cache = MemoryCacheBackend()
    worker = WorkerCapability(
        worker_id="cpu-worker-cancel-api",
        queue="cpu-worker-cancel-api",
        executor_types=("docker_image",),
        tiers=("heavy",),
        cpu_capacity=8,
        memory_capacity_gb=16,
        parallelism=2,
    )
    task = _task()
    task.id = "task-worker-cancel-api"
    task.status = TaskStatus.RUNNING.value
    task.tool_id = "tool-worker-queue"
    task.tool_version_id = "version-worker-queue"
    task.started_at = None
    task.finished_at = None
    task.execution_time_sec = None
    task.progress = 20.0
    task.progress_message = "执行中"
    task.celery_task_id = None
    task.extra_data["execution_attempt_id"] = "attempt-1"
    task.extra_data["dispatch"] = {
        "resource_reservation": {
            "worker_id": worker.worker_id,
            "lease_id": f"{task.id}:attempt-1",
            "ttl_seconds": 60,
            "status": "claimed",
        }
    }
    request = resource_request_from_snapshot(
        _tool_version().config,
        task.extra_data["resource_snapshot"],
    )
    manager = WorkerResourceLeaseManager(cache=cache)
    assert (
        await manager.acquire(
            capability=worker,
            request=request,
            lease_id=f"{task.id}:attempt-1",
            ttl_seconds=60,
            lease_phase="running",
            user_id=task.user_id,
            project_id=task.project_id,
        )
    ).acquired is True

    monkeypatch.setattr("app.cache.get_cache", lambda: cache)
    monkeypatch.setattr(
        "app.tasks.cancellation.use_direct_task_execution",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.tasks.cancellation.finish_task_execution_record_best_effort",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.tasks.cancellation.get_audit_logger",
        lambda: SimpleNamespace(log_task_operation=lambda **kwargs: None),
    )

    canceled = await cancel_platform_task(
        None,
        task=task,
        current_user=SimpleNamespace(id="user-worker-cancel"),
        direct_runner=SimpleNamespace(cancel_task=lambda task_id: True),
    )

    assert canceled is True
    assert task.status == TaskStatus.CANCELED.value
    assert task.extra_data["dispatch"]["resource_reservation"]["status"] == "claimed"
    assert await manager.current_usage(worker.worker_id) == {
        "cpu": 4.0,
        "memory_gb": 8.0,
        "parallelism": 1,
    }


@pytest.mark.asyncio
async def test_resource_lease_release_does_not_confirm_execution_exit():
    task = _task()
    task.id = "task-cancel-release-boundary"
    task.extra_data["execution_attempt_id"] = "attempt-1"
    task.extra_data["execution_control"] = {
        "state": "cancel_requested",
        "attempt_id": "attempt-1",
    }
    cache = MemoryCacheBackend()

    await release_task_resource_reservation(
        task,
        reason="executor_finally",
        attempt_id="attempt-1",
        cache=cache,
    )

    assert is_task_cancellation_pending(task) is True


@pytest.mark.asyncio
async def test_pending_task_cancel_releases_resource_reservation_immediately(monkeypatch):
    cache = MemoryCacheBackend()
    worker = WorkerCapability(
        worker_id="cpu-worker-cancel-pending",
        queue="cpu-worker-cancel-pending",
        executor_types=("docker_image",),
        tiers=("heavy",),
        cpu_capacity=8,
        memory_capacity_gb=16,
        parallelism=2,
    )
    task = _task()
    task.id = "task-worker-cancel-pending"
    task.status = TaskStatus.PENDING.value
    task.tool_id = "tool-worker-queue"
    task.tool_version_id = "version-worker-queue"
    task.started_at = None
    task.finished_at = None
    task.execution_time_sec = None
    task.progress = 0.0
    task.progress_message = "等待执行"
    task.celery_task_id = None
    task.extra_data["execution_attempt_id"] = "attempt-1"
    task.extra_data["dispatch"] = {
        "resource_reservation": {
            "worker_id": worker.worker_id,
            "lease_id": f"{task.id}:attempt-1",
            "ttl_seconds": 60,
            "status": "reserved",
        }
    }
    request = resource_request_from_snapshot(
        _tool_version().config,
        task.extra_data["resource_snapshot"],
    )
    manager = WorkerResourceLeaseManager(cache=cache)
    assert (
        await manager.acquire(
            capability=worker,
            request=request,
            lease_id=f"{task.id}:attempt-1",
            ttl_seconds=60,
            lease_phase="reserved",
        )
    ).acquired is True

    monkeypatch.setattr("app.cache.get_cache", lambda: cache)
    monkeypatch.setattr(
        "app.tasks.cancellation.use_direct_task_execution",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.tasks.cancellation.finish_task_execution_record_best_effort",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.tasks.cancellation.get_audit_logger",
        lambda: SimpleNamespace(log_task_operation=lambda **kwargs: None),
    )

    canceled = await cancel_platform_task(
        None,
        task=task,
        current_user=SimpleNamespace(id="user-worker-cancel-pending"),
        direct_runner=SimpleNamespace(cancel_task=lambda task_id: True),
    )

    assert canceled is True
    assert task.status == TaskStatus.CANCELED.value
    assert task.extra_data["dispatch"]["resource_reservation"]["status"] == "released"
    assert await manager.current_usage(worker.worker_id) == {
        "cpu": 0.0,
        "memory_gb": 0.0,
        "parallelism": 0,
    }


@pytest.mark.asyncio
async def test_running_task_delete_defers_resource_lease_release(monkeypatch):
    cache = MemoryCacheBackend()
    worker = WorkerCapability(
        worker_id="cpu-worker-delete-running",
        queue="cpu-worker-delete-running",
        executor_types=("docker_image",),
        tiers=("heavy",),
        cpu_capacity=8,
        memory_capacity_gb=16,
        parallelism=2,
    )
    task = _task()
    task.id = "task-worker-delete-running"
    task.status = TaskStatus.RUNNING.value
    task.extra_data["execution_attempt_id"] = "attempt-1"
    task.extra_data["dispatch"] = {
        "resource_reservation": {
            "worker_id": worker.worker_id,
            "lease_id": f"{task.id}:attempt-1",
            "ttl_seconds": 60,
            "status": "claimed",
        }
    }
    request = resource_request_from_snapshot(
        _tool_version().config,
        task.extra_data["resource_snapshot"],
    )
    manager = WorkerResourceLeaseManager(cache=cache)
    assert (
        await manager.acquire(
            capability=worker,
            request=request,
            lease_id=f"{task.id}:attempt-1",
            ttl_seconds=60,
            lease_phase="running",
            user_id=task.user_id,
            project_id=task.project_id,
        )
    ).acquired is True

    class FakeResult:
        def scalar_one_or_none(self):
            return task

    class FakeDB:
        deleted = False

        async def execute(self, *args, **kwargs):
            return FakeResult()

        async def delete(self, value):
            self.deleted = True
            assert value is task

        async def get(self, model, entity_id):
            return None

        async def commit(self):
            return None

    db = FakeDB()
    revoked = []
    monkeypatch.setattr("app.cache.get_cache", lambda: cache)
    monkeypatch.setattr(
        "app.tasks.cancellation.use_direct_task_execution",
        lambda: False,
    )
    monkeypatch.setattr(
        TaskQueueManager,
        "revoke_task",
        classmethod(lambda cls, task_id: revoked.append(task_id)),
    )
    monkeypatch.setattr(
        "app.tasks.cancellation.finish_task_execution_record_best_effort",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.tasks.cancellation.get_audit_logger",
        lambda: SimpleNamespace(log_task_operation=lambda **kwargs: None),
    )
    task.tool_id = "tool-worker-delete-running"
    task.tool_version_id = None
    task.celery_task_id = "celery-running-delete"
    task.started_at = None
    task.progress = 0.0

    deleted = await delete_task(
        task_id=task.id,
        current_user=SimpleNamespace(id="admin-user"),
        db=db,
    )

    assert deleted["message"] == "运行中任务已发起取消，记录保留"
    assert db.deleted is False
    assert revoked == ["celery-running-delete"]
    assert task.status == TaskStatus.CANCELED.value
    assert is_task_cancellation_pending(task) is True
    assert await manager.current_usage(worker.worker_id) == {
        "cpu": 4.0,
        "memory_gb": 8.0,
        "parallelism": 1,
    }


@pytest.mark.asyncio
async def test_delete_rejects_cancellation_timeout_tombstone():
    task = _task()
    task.id = "task-worker-delete-timeout"
    task.status = TaskStatus.CANCELED.value
    task.extra_data["execution_control"] = {
        "state": "cancel_timeout",
        "attempt_id": "attempt-old",
        "manual_intervention_required": True,
    }

    class FakeResult:
        def scalar_one_or_none(self):
            return task

    class FakeDB:
        async def execute(self, *args, **kwargs):
            return FakeResult()

        async def delete(self, value):
            raise AssertionError("cancellation tombstone must not be deleted")

    with pytest.raises(ConflictException, match="尚未确认停止"):
        await delete_task(
            task_id=task.id,
            current_user=SimpleNamespace(id="admin-user"),
            db=FakeDB(),
        )
