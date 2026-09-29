"""纯后端 Worker 队列并发准入测试。"""

import asyncio

import pytest

from app.cache.memory import MemoryCacheBackend
from app.tasks.resource_admission import WorkerCapability
from app.tasks.resource_lease import WorkerResourceLeaseManager
from app.tasks.resource_profile import ResourceRequest
from app.tasks.worker_capability_registry import WorkerCapabilityRegistry


def _request() -> ResourceRequest:
    return ResourceRequest(
        executor_type="docker_image",
        tier="heavy",
        cpu=4,
        memory_gb=8,
        cpu_limit=4,
        memory_limit="8g",
        gpu_required=False,
        gpu_count=0,
        gpu_memory_mb=0,
        timeout_sec=600,
        parallelism=1,
    )


@pytest.mark.asyncio
async def test_concurrent_reservations_do_not_overbook_single_worker():
    cache = MemoryCacheBackend()
    worker = WorkerCapability(
        worker_id="cpu-worker-concurrent",
        queue="cpu-worker-concurrent",
        executor_types=("docker_image",),
        tiers=("heavy",),
        cpu_capacity=4,
        memory_capacity_gb=8,
        parallelism=1,
    )
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)
    await registry.register(worker)

    reservation_ids = (
        "task-concurrent-1:attempt-1",
        "task-concurrent-2:attempt-1",
    )
    decisions = await asyncio.gather(
        *(
            registry.reserve_worker(
                _request(),
                reservation_id=reservation_id,
                ttl_seconds=60,
            )
            for reservation_id in reservation_ids
        )
    )

    admitted = [decision for decision in decisions if decision.admitted]
    rejected = [decision for decision in decisions if not decision.admitted]
    assert len(admitted) == 1
    assert len(rejected) == 1
    assert rejected[0].reason in {
        "resource_lock_busy",
        "cpu_capacity_exhausted",
        "memory_capacity_exhausted",
        "parallelism_capacity_exhausted",
    }

    manager = WorkerResourceLeaseManager(cache=cache)
    assert await manager.current_lease_phase_counts(worker.worker_id) == {
        "reserved": 1,
        "running": 0,
        "unknown": 0,
    }
    assert await manager.current_usage(worker.worker_id) == {
        "cpu": 4.0,
        "memory_gb": 8.0,
        "parallelism": 1,
    }

    winner_index = next(
        index for index, decision in enumerate(decisions) if decision.admitted
    )
    assert await manager.release(
        worker_id=worker.worker_id,
        lease_id=reservation_ids[winner_index],
    ) is True

    retry = await registry.reserve_worker(
        _request(),
        reservation_id="task-concurrent-retry:attempt-2",
        ttl_seconds=60,
    )
    assert retry.admitted is True
    assert retry.worker_id == worker.worker_id
    assert await manager.release(
        worker_id=worker.worker_id,
        lease_id="task-concurrent-retry:attempt-2",
    ) is True
