"""任务分发资源准入元数据测试。"""

from types import SimpleNamespace
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.cache.memory import MemoryCacheBackend
from app.config import settings
from app.tasks.service import dispatch_tool_task
from app.tasks.worker_capability_registry import WorkerCapabilityRegistry
from app.tasks.resource_admission import WorkerCapability
from app.tasks.queue_manager import TaskQueueManager
from app.common.time import utcnow


def _tool_version() -> SimpleNamespace:
    return SimpleNamespace(
        id="version-1",
        config={
            "type": "docker_image",
            "resource_profile": {
                "tier": "heavy",
                "cpu": 8,
                "memory_gb": 32,
                "parallelism": 1,
            },
        },
    )


def _task() -> SimpleNamespace:
    return SimpleNamespace(
        id="task-1",
        user_id="user-1",
        priority="normal",
        status="PENDING",
        extra_data={
            "resource_snapshot": {
                "resource_request": {
                    "executor_type": "docker_image",
                    "tier": "heavy",
                    "cpu": 8.0,
                    "memory_gb": 32.0,
                    "cpu_limit": 8.0,
                    "memory_limit": "32g",
                    "gpu_required": False,
                    "gpu_count": 0,
                    "gpu_memory_mb": 0,
                    "timeout_sec": 600,
                    "parallelism": 1,
                },
                "gpu_required": False,
            }
        },
        celery_task_id=None,
    )


@pytest.mark.asyncio
async def test_dispatch_records_admitted_worker_in_dispatch_metadata(monkeypatch):
    cache = MemoryCacheBackend()
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)
    await registry.register(
        WorkerCapability(
            worker_id="cpu-worker-1",
            executor_types=("docker_image",),
            tiers=("heavy",),
            cpu_capacity=16,
            memory_capacity_gb=64,
            parallelism=2,
        )
    )
    monkeypatch.setattr("app.cache.get_cache", lambda: cache)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ADMISSION_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: False)

    monkeypatch.setattr(
        TaskQueueManager,
        "enqueue_task",
        classmethod(lambda cls, **kwargs: SimpleNamespace(id="celery-1")),
    )

    task = _task()
    db = SimpleNamespace(commit=AsyncMock())

    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=_tool_version(),
        user_role="user",
    )

    assert task.extra_data["dispatch"]["resource_admission"] == {
        "status": "admitted",
        "worker_id": "cpu-worker-1",
        "reason": None,
    }


@pytest.mark.asyncio
async def test_dispatch_passes_aged_priority_to_celery(monkeypatch):
    monkeypatch.setattr(settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: False)
    monkeypatch.setattr(
        TaskQueueManager,
        "enqueue_task",
        classmethod(lambda cls, **kwargs: SimpleNamespace(id="celery-aged")),
    )

    task = _task()
    task.created_at = utcnow() - timedelta(seconds=900)
    db = SimpleNamespace(commit=AsyncMock())

    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=_tool_version(),
        user_role="user",
    )

    assert task.extra_data["dispatch"]["queue"] == "heavy_compute"
    assert task.extra_data["dispatch"]["queue_priority"] == 7
    assert task.extra_data["dispatch"]["wait_seconds"] == 900
    assert task.extra_data["dispatch"]["priority_boost"] == 3


@pytest.mark.asyncio
async def test_dispatch_keeps_unknown_when_registry_has_no_workers(monkeypatch):
    monkeypatch.setattr("app.cache.get_cache", lambda: MemoryCacheBackend())
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ADMISSION_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ROUTING_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: False)
    monkeypatch.setattr(
        TaskQueueManager,
        "enqueue_task",
        classmethod(lambda cls, **kwargs: SimpleNamespace(id="celery-2")),
    )

    task = _task()
    db = SimpleNamespace(commit=AsyncMock())

    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=_tool_version(),
        user_role="user",
    )

    assert task.extra_data["dispatch"]["resource_admission"] == {
        "status": "unknown",
        "worker_id": None,
        "reason": "no_registered_workers",
    }
    assert task.extra_data["dispatch"]["queue"] == "heavy_compute"


@pytest.mark.asyncio
async def test_dispatch_continues_when_admission_observation_fails(monkeypatch):
    def broken_cache():
        raise RuntimeError("cache unavailable")

    monkeypatch.setattr("app.cache.get_cache", broken_cache)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ADMISSION_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: False)
    monkeypatch.setattr(
        TaskQueueManager,
        "enqueue_task",
        classmethod(lambda cls, **kwargs: SimpleNamespace(id="celery-3")),
    )

    task = _task()
    db = SimpleNamespace(commit=AsyncMock())

    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=_tool_version(),
        user_role="user",
    )

    assert task.celery_task_id == "celery-3"
    assert task.extra_data["dispatch"]["resource_admission"] == {
        "status": "unknown",
        "worker_id": None,
        "reason": "admission_check_unavailable",
    }


@pytest.mark.asyncio
async def test_dispatch_records_rejected_without_blocking_enqueue(monkeypatch):
    cache = MemoryCacheBackend()
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)
    await registry.register(
        WorkerCapability(
            worker_id="small-worker-1",
            executor_types=("docker_image",),
            tiers=("heavy",),
            cpu_capacity=2,
            memory_capacity_gb=8,
            parallelism=1,
        )
    )
    monkeypatch.setattr("app.cache.get_cache", lambda: cache)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ADMISSION_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: False)
    monkeypatch.setattr(
        TaskQueueManager,
        "enqueue_task",
        classmethod(lambda cls, **kwargs: SimpleNamespace(id="celery-4")),
    )

    task = _task()
    db = SimpleNamespace(commit=AsyncMock())

    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=_tool_version(),
        user_role="user",
    )

    assert task.celery_task_id == "celery-4"
    assert task.extra_data["dispatch"]["resource_admission"] == {
        "status": "rejected",
        "worker_id": None,
        "reason": "no_capable_worker",
    }


@pytest.mark.asyncio
async def test_dispatch_routes_to_declared_worker_queue_when_enabled(monkeypatch):
    cache = MemoryCacheBackend()
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)
    await registry.register(
        WorkerCapability(
            worker_id="cpu-worker-1",
            queue="cpu-worker-queue",
            executor_types=("docker_image",),
            tiers=("heavy",),
            cpu_capacity=16,
            memory_capacity_gb=64,
            parallelism=2,
        )
    )
    monkeypatch.setattr("app.cache.get_cache", lambda: cache)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ADMISSION_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ROUTING_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: False)
    monkeypatch.setattr(
        TaskQueueManager,
        "enqueue_task",
        classmethod(lambda cls, **kwargs: SimpleNamespace(id="celery-routed")),
    )

    task = _task()
    db = SimpleNamespace(commit=AsyncMock())

    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=_tool_version(),
        user_role="user",
    )

    assert task.extra_data["dispatch"]["queue"] == "cpu-worker-queue"
    assert task.extra_data["dispatch"]["resource_admission"] == {
        "status": "admitted",
        "worker_id": "cpu-worker-1",
        "reason": None,
        "queue": "cpu-worker-queue",
    }


@pytest.mark.asyncio
async def test_dispatch_skips_saturated_worker_and_routes_to_available_worker(monkeypatch):
    cache = MemoryCacheBackend()
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)
    busy_worker = WorkerCapability(
        worker_id="busy-worker",
        queue="busy-worker-queue",
        executor_types=("docker_image",),
        tiers=("heavy",),
        cpu_capacity=8,
        memory_capacity_gb=32,
        parallelism=1,
    )
    available_worker = WorkerCapability(
        worker_id="available-worker",
        queue="available-worker-queue",
        executor_types=("docker_image",),
        tiers=("heavy",),
        cpu_capacity=8,
        memory_capacity_gb=32,
        parallelism=1,
    )
    await registry.register(busy_worker)
    await registry.register(available_worker)

    from app.tasks.resource_lease import WorkerResourceLeaseManager
    from app.tasks.resource_profile import resource_request_from_snapshot

    await WorkerResourceLeaseManager(cache=cache).acquire(
        capability=busy_worker,
        request=resource_request_from_snapshot(
            _tool_version().config,
            _task().extra_data["resource_snapshot"],
        ),
        lease_id="busy-task-attempt-1",
    )

    monkeypatch.setattr("app.cache.get_cache", lambda: cache)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ADMISSION_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ROUTING_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: False)
    monkeypatch.setattr(
        TaskQueueManager,
        "enqueue_task",
        classmethod(lambda cls, **kwargs: SimpleNamespace(id="celery-available")),
    )

    task = _task()
    db = SimpleNamespace(commit=AsyncMock())

    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=_tool_version(),
        user_role="user",
    )

    assert task.extra_data["dispatch"]["queue"] == "available-worker-queue"
    assert task.extra_data["dispatch"]["resource_admission"] == {
        "status": "admitted",
        "worker_id": "available-worker",
        "reason": None,
        "queue": "available-worker-queue",
    }


@pytest.mark.asyncio
async def test_dispatch_records_and_reuses_resource_reservation(monkeypatch):
    cache = MemoryCacheBackend()
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)
    await registry.register(
        WorkerCapability(
            worker_id="reserved-worker",
            queue="reserved-worker-queue",
            executor_types=("docker_image",),
            tiers=("heavy",),
            cpu_capacity=16,
            memory_capacity_gb=64,
            parallelism=2,
        )
    )
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
        classmethod(lambda cls, **kwargs: SimpleNamespace(id="celery-reserved")),
    )

    task = _task()
    db = SimpleNamespace(commit=AsyncMock())

    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=_tool_version(),
        user_role="user",
    )

    reservation = task.extra_data["dispatch"]["resource_reservation"]
    assert reservation == {
        "worker_id": "reserved-worker",
        "lease_id": f"{task.id}:{task.extra_data['execution_attempt_id']}",
        "ttl_seconds": 60,
        "status": "reserved",
    }
    assert task.extra_data["dispatch"]["queue"] == "reserved-worker-queue"


@pytest.mark.asyncio
async def test_dispatch_keeps_quota_rejection_observable_without_failing_enqueue(monkeypatch):
    cache = MemoryCacheBackend()
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)
    await registry.register(
        WorkerCapability(
            worker_id="quota-worker",
            queue="quota-worker-queue",
            executor_types=("docker_image",),
            tiers=("heavy",),
            cpu_capacity=32,
            memory_capacity_gb=64,
            parallelism=8,
        )
    )
    monkeypatch.setattr("app.cache.get_cache", lambda: cache)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ADMISSION_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ROUTING_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_RESERVATION_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "RESOURCE_SCOPE_QUOTA_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "RESOURCE_USER_MAX_PARALLELISM", 1, raising=False)
    monkeypatch.setattr(settings, "RESOURCE_PROJECT_MAX_PARALLELISM", None, raising=False)
    monkeypatch.setattr(settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: False)
    monkeypatch.setattr(
        TaskQueueManager,
        "enqueue_task",
        classmethod(lambda cls, **kwargs: SimpleNamespace(id=f"celery-{kwargs['task_id']}")),
    )

    first = _task()
    first.id = "quota-task-1"
    second = _task()
    second.id = "quota-task-2"
    db = SimpleNamespace(commit=AsyncMock())

    await dispatch_tool_task(
        db=db,
        task=first,
        tool_version=_tool_version(),
        user_role="user",
    )
    await dispatch_tool_task(
        db=db,
        task=second,
        tool_version=_tool_version(),
        user_role="user",
    )

    assert first.extra_data["dispatch"]["resource_admission"]["status"] == "admitted"
    assert second.extra_data["dispatch"]["resource_admission"] == {
        "status": "rejected",
        "worker_id": None,
        "reason": "user_parallelism_quota_exhausted",
    }
    assert second.celery_task_id == "celery-quota-task-2"


@pytest.mark.asyncio
async def test_dispatch_releases_resource_reservation_when_enqueue_fails(monkeypatch):
    cache = MemoryCacheBackend()
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)
    worker = WorkerCapability(
        worker_id="reserved-worker",
        queue="reserved-worker-queue",
        executor_types=("docker_image",),
        tiers=("heavy",),
        cpu_capacity=16,
        memory_capacity_gb=64,
        parallelism=2,
    )
    await registry.register(worker)
    monkeypatch.setattr("app.cache.get_cache", lambda: cache)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ADMISSION_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ROUTING_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_RESERVATION_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "RESOURCE_DISPATCH_RESERVATION_TTL_SECONDS", 60, raising=False)
    monkeypatch.setattr(settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: False)

    def fail_enqueue(cls, **kwargs):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(TaskQueueManager, "enqueue_task", classmethod(fail_enqueue))

    task = _task()
    db = SimpleNamespace(commit=AsyncMock())

    with pytest.raises(Exception):
        await dispatch_tool_task(
            db=db,
            task=task,
            tool_version=_tool_version(),
            user_role="user",
        )

    from app.tasks.resource_lease import WorkerResourceLeaseManager

    assert await WorkerResourceLeaseManager(cache=cache).current_usage(worker.worker_id) == {
        "cpu": 0.0,
        "memory_gb": 0.0,
        "parallelism": 0,
    }
