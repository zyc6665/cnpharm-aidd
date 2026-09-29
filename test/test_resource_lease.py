"""Worker 动态资源租约测试。"""

import pytest
from datetime import timedelta
from types import SimpleNamespace

from app.cache.memory import MemoryCacheBackend
from app.common.time import utcnow
from app.config import settings
from app.tasks.resource_admission import WorkerCapability
from app.tasks.resource_lease import (
    WorkerResourceLeaseManager,
    release_task_resource_reservation,
)
from app.tasks.resource_profile import ResourceRequest


def _request(
    *,
    cpu: float | None = 4,
    memory_gb: float | None = 8,
    parallelism: int = 1,
) -> ResourceRequest:
    return ResourceRequest(
        executor_type="docker_image",
        tier="heavy",
        cpu=cpu,
        memory_gb=memory_gb,
        cpu_limit=cpu,
        memory_limit=f"{memory_gb:g}g" if memory_gb is not None else None,
        gpu_required=False,
        gpu_count=0,
        gpu_memory_mb=0,
        timeout_sec=600,
        parallelism=parallelism,
    )


@pytest.mark.asyncio
async def test_resource_lease_blocks_capacity_and_release_frees_it():
    cache = MemoryCacheBackend()
    manager = WorkerResourceLeaseManager(cache=cache)
    capability = WorkerCapability(
        worker_id="cpu-worker-1",
        cpu_capacity=8,
        memory_capacity_gb=16,
        parallelism=2,
    )

    first = await manager.acquire(
        capability=capability,
        request=_request(),
        lease_id="task-1-attempt-1",
    )
    second = await manager.acquire(
        capability=capability,
        request=_request(),
        lease_id="task-2-attempt-1",
    )
    third = await manager.acquire(
        capability=capability,
        request=_request(),
        lease_id="task-3-attempt-1",
    )

    assert first.acquired is True
    assert second.acquired is True
    assert third.acquired is False
    assert third.reason == "cpu_capacity_exhausted"

    assert await manager.release(
        worker_id=capability.worker_id,
        lease_id="task-1-attempt-1",
    ) is True
    recovered = await manager.acquire(
        capability=capability,
        request=_request(),
        lease_id="task-3-attempt-1",
    )
    assert recovered.acquired is True


@pytest.mark.asyncio
async def test_resource_lease_enforces_memory_and_parallelism_limits():
    cache = MemoryCacheBackend()
    manager = WorkerResourceLeaseManager(cache=cache)

    memory_capability = WorkerCapability(
        worker_id="memory-worker-1",
        memory_capacity_gb=8,
        parallelism=4,
    )
    memory_first = await manager.acquire(
        capability=memory_capability,
        request=_request(cpu=None, memory_gb=8),
        lease_id="memory-task-1",
    )
    memory_second = await manager.acquire(
        capability=memory_capability,
        request=_request(cpu=None, memory_gb=1),
        lease_id="memory-task-2",
    )

    parallelism_capability = WorkerCapability(
        worker_id="parallel-worker-1",
        parallelism=1,
    )
    parallel_first = await manager.acquire(
        capability=parallelism_capability,
        request=_request(cpu=None, memory_gb=None),
        lease_id="parallel-task-1",
    )
    parallel_second = await manager.acquire(
        capability=parallelism_capability,
        request=_request(cpu=None, memory_gb=None),
        lease_id="parallel-task-2",
    )

    assert memory_first.acquired is True
    assert memory_second.acquired is False
    assert memory_second.reason == "memory_capacity_exhausted"
    assert parallel_first.acquired is True
    assert parallel_second.acquired is False
    assert parallel_second.reason == "parallelism_capacity_exhausted"


@pytest.mark.asyncio
async def test_resource_lease_acquire_is_idempotent_and_heartbeat_refreshes():
    cache = MemoryCacheBackend()
    manager = WorkerResourceLeaseManager(cache=cache)
    capability = WorkerCapability(
        worker_id="cpu-worker-1",
        cpu_capacity=8,
        parallelism=1,
    )
    request = _request(memory_gb=None)

    first = await manager.acquire(
        capability=capability,
        request=request,
        lease_id="task-1-attempt-1",
        ttl_seconds=30,
    )
    duplicate = await manager.acquire(
        capability=capability,
        request=request,
        lease_id="task-1-attempt-1",
        ttl_seconds=30,
    )

    assert first.acquired is True
    assert duplicate.acquired is True
    assert await manager.heartbeat(
        worker_id=capability.worker_id,
        lease_id="task-1-attempt-1",
        ttl_seconds=30,
    ) is True
    usage = await manager.current_usage(capability.worker_id)
    assert usage == {"cpu": 4.0, "memory_gb": 0.0, "parallelism": 1}


@pytest.mark.asyncio
async def test_resource_lease_transitions_from_reserved_to_running():
    cache = MemoryCacheBackend()
    manager = WorkerResourceLeaseManager(cache=cache)
    capability = WorkerCapability(
        worker_id="cpu-worker-1",
        cpu_capacity=8,
        memory_capacity_gb=16,
        parallelism=2,
    )
    request = _request()
    lease_id = "task-1:attempt-1"

    reserved = await manager.acquire(
        capability=capability,
        request=request,
        lease_id=lease_id,
        lease_phase="reserved",
    )
    assert reserved.acquired is True
    assert await manager.current_lease_phase_counts(capability.worker_id) == {
        "reserved": 1,
        "running": 0,
        "unknown": 0,
    }

    running = await manager.acquire(
        capability=capability,
        request=request,
        lease_id=lease_id,
        lease_phase="running",
    )
    assert running.acquired is True
    assert await manager.current_lease_phase_counts(capability.worker_id) == {
        "reserved": 0,
        "running": 1,
        "unknown": 0,
    }


@pytest.mark.asyncio
async def test_resource_lease_reclaims_stale_reservations():
    cache = MemoryCacheBackend()
    capability = WorkerCapability(
        worker_id="stale-worker",
        cpu_capacity=8,
        memory_capacity_gb=16,
        parallelism=2,
    )
    stale_clock = lambda: utcnow() - timedelta(seconds=600)
    stale_manager = WorkerResourceLeaseManager(cache=cache, clock=stale_clock)
    await stale_manager.acquire(
        capability=capability,
        request=_request(),
        lease_id="stale-task:attempt-1",
        lease_phase="reserved",
    )

    reclaimed = await WorkerResourceLeaseManager(cache=cache).reclaim_stale_reservations(
        max_age_seconds=300,
    )

    assert reclaimed == 1
    assert await WorkerResourceLeaseManager(cache=cache).current_usage(
        capability.worker_id,
    ) == {
        "cpu": 0.0,
        "memory_gb": 0.0,
        "parallelism": 0,
    }


@pytest.mark.asyncio
async def test_resource_lease_enforces_user_and_project_parallelism_quotas(monkeypatch):
    monkeypatch.setattr(settings, "RESOURCE_SCOPE_QUOTA_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "RESOURCE_USER_MAX_PARALLELISM", 1, raising=False)
    monkeypatch.setattr(settings, "RESOURCE_PROJECT_MAX_PARALLELISM", 2, raising=False)

    cache = MemoryCacheBackend()
    manager = WorkerResourceLeaseManager(cache=cache)
    capability = WorkerCapability(
        worker_id="quota-worker",
        cpu_capacity=32,
        memory_capacity_gb=64,
        parallelism=8,
    )

    first = await manager.acquire(
        capability=capability,
        request=_request(),
        lease_id="user-1-task",
        user_id="user-1",
        project_id="project-1",
    )
    same_user = await manager.acquire(
        capability=capability,
        request=_request(),
        lease_id="user-1-task-2",
        user_id="user-1",
        project_id="project-2",
    )
    same_project = await manager.acquire(
        capability=capability,
        request=_request(),
        lease_id="user-2-task",
        user_id="user-2",
        project_id="project-1",
    )
    project_overflow = await manager.acquire(
        capability=capability,
        request=_request(),
        lease_id="user-3-task",
        user_id="user-3",
        project_id="project-1",
    )

    assert first.acquired is True
    assert same_user.acquired is False
    assert same_user.reason == "user_parallelism_quota_exhausted"
    assert same_project.acquired is True
    assert project_overflow.acquired is False
    assert project_overflow.reason == "project_parallelism_quota_exhausted"


@pytest.mark.asyncio
async def test_resource_lease_enforces_scope_cpu_memory_and_parallelism_quotas(
    monkeypatch,
):
    """用户 scope 配额应统一限制 CPU、内存和并发，并记录拒绝原因。"""
    monkeypatch.setattr(settings, "RESOURCE_SCOPE_QUOTA_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "RESOURCE_USER_MAX_CPU", 4, raising=False)
    monkeypatch.setattr(settings, "RESOURCE_USER_MAX_MEMORY_GB", 8, raising=False)
    monkeypatch.setattr(settings, "RESOURCE_USER_MAX_PARALLELISM", 2, raising=False)

    cache = MemoryCacheBackend()
    manager = WorkerResourceLeaseManager(cache=cache)
    capability = WorkerCapability(
        worker_id="quota-dimension-worker",
        cpu_capacity=32,
        memory_capacity_gb=64,
        parallelism=8,
    )

    cpu_first = await manager.acquire(
        capability=capability,
        request=_request(cpu=4, memory_gb=None, parallelism=1),
        lease_id="cpu-task-1",
        user_id="dimension-user",
    )
    cpu_overflow = await manager.acquire(
        capability=capability,
        request=_request(cpu=1, memory_gb=None, parallelism=1),
        lease_id="cpu-task-2",
        user_id="dimension-user",
    )
    assert cpu_first.acquired is True
    assert cpu_overflow.reason == "user_cpu_quota_exhausted"

    await manager.release(
        worker_id=capability.worker_id,
        lease_id="cpu-task-1",
    )
    memory_first = await manager.acquire(
        capability=capability,
        request=_request(cpu=None, memory_gb=8, parallelism=1),
        lease_id="memory-task-1",
        user_id="dimension-user",
    )
    memory_overflow = await manager.acquire(
        capability=capability,
        request=_request(cpu=None, memory_gb=1, parallelism=1),
        lease_id="memory-task-2",
        user_id="dimension-user",
    )
    assert memory_first.acquired is True
    assert memory_overflow.reason == "user_memory_quota_exhausted"

    await manager.release(
        worker_id=capability.worker_id,
        lease_id="memory-task-1",
    )
    parallel_first = await manager.acquire(
        capability=capability,
        request=_request(cpu=None, memory_gb=None, parallelism=2),
        lease_id="parallel-task-1",
        user_id="dimension-user",
    )
    parallel_overflow = await manager.acquire(
        capability=capability,
        request=_request(cpu=None, memory_gb=None, parallelism=1),
        lease_id="parallel-task-2",
        user_id="dimension-user",
    )

    assert parallel_first.acquired is True
    assert parallel_overflow.reason == "user_parallelism_quota_exhausted"
    snapshot = await manager.quota_manager.current_scope_snapshot()
    assert snapshot["user"]["dimension-user"]["usage"] == {
        "cpu": 0.0,
        "memory_gb": 0.0,
        "parallelism": 2,
    }
    assert snapshot["user"]["dimension-user"]["rejection_counts"] == {
        "user_cpu_quota_exhausted": 1,
        "user_memory_quota_exhausted": 1,
        "user_parallelism_quota_exhausted": 1,
    }


@pytest.mark.asyncio
async def test_release_task_resource_reservation_updates_lifecycle_metadata():
    cache = MemoryCacheBackend()
    manager = WorkerResourceLeaseManager(cache=cache)
    capability = WorkerCapability(
        worker_id="cpu-worker-1",
        cpu_capacity=8,
        memory_capacity_gb=16,
        parallelism=2,
    )
    request = _request()
    lease_id = "task-1:attempt-1"
    await manager.acquire(
        capability=capability,
        request=request,
        lease_id=lease_id,
    )
    task = SimpleNamespace(
        id="task-1",
        extra_data={
            "dispatch": {
                "resource_reservation": {
                    "worker_id": capability.worker_id,
                    "lease_id": lease_id,
                    "ttl_seconds": 60,
                }
            }
        },
    )

    updated = await release_task_resource_reservation(
        task,
        reason="task_canceled",
        cache=cache,
    )

    assert updated is True
    reservation = task.extra_data["dispatch"]["resource_reservation"]
    assert reservation["status"] == "released"
    assert reservation["release_reason"] == "task_canceled"
    assert reservation["released_at"]
    assert await manager.current_usage(capability.worker_id) == {
        "cpu": 0.0,
        "memory_gb": 0.0,
        "parallelism": 0,
    }


@pytest.mark.asyncio
async def test_release_task_resource_reservation_ignores_stale_attempt():
    cache = MemoryCacheBackend()
    manager = WorkerResourceLeaseManager(cache=cache)
    capability = WorkerCapability(
        worker_id="cpu-worker-1",
        cpu_capacity=8,
        memory_capacity_gb=16,
        parallelism=2,
    )
    lease_id = "task-1:attempt-2"
    await manager.acquire(
        capability=capability,
        request=_request(),
        lease_id=lease_id,
    )
    task = SimpleNamespace(
        id="task-1",
        extra_data={
            "dispatch": {
                "resource_reservation": {
                    "worker_id": capability.worker_id,
                    "lease_id": lease_id,
                    "ttl_seconds": 60,
                }
            }
        },
    )

    updated = await release_task_resource_reservation(
        task,
        reason="stale_attempt",
        attempt_id="attempt-1",
        cache=cache,
    )

    assert updated is False
    assert "status" not in task.extra_data["dispatch"]["resource_reservation"]
    assert await manager.current_usage(capability.worker_id) == {
        "cpu": 4.0,
        "memory_gb": 8.0,
        "parallelism": 1,
    }
