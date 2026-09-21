"""任务分发资源准入元数据测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cache.memory import MemoryCacheBackend
from app.config import settings
from app.tasks.service import dispatch_tool_task
from app.tasks.worker_capability_registry import WorkerCapabilityRegistry
from app.tasks.resource_admission import WorkerCapability
from app.tasks.queue_manager import TaskQueueManager


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
async def test_dispatch_keeps_unknown_when_registry_has_no_workers(monkeypatch):
    monkeypatch.setattr("app.cache.get_cache", lambda: MemoryCacheBackend())
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_ADMISSION_ENABLED", True, raising=False)
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
