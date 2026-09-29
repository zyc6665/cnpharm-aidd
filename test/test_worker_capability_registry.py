"""Worker capability registry 测试。"""

import pytest

from app.cache.memory import MemoryCacheBackend
from app.tasks.resource_admission import ResourceAdmissionPolicy, WorkerCapability
from app.tasks.resource_lease import WorkerResourceLeaseManager
from app.tasks.resource_profile import ResourceRequest
from app.tasks.worker_capability_registry import WorkerCapabilityRegistry


def _capability(worker_id: str = "gpu-worker-1") -> WorkerCapability:
    return WorkerCapability(
        worker_id=worker_id,
        queue=f"queue-{worker_id}",
        executor_types=("docker_image",),
        tiers=("heavy",),
        cpu_capacity=16,
        memory_capacity_gb=64,
        gpu_count=2,
        gpu_memory_mb=24576,
        parallelism=2,
    )


def _request() -> ResourceRequest:
    return ResourceRequest(
        executor_type="docker_image",
        tier="heavy",
        cpu=8,
        memory_gb=32,
        cpu_limit=8,
        memory_limit="32g",
        gpu_required=True,
        gpu_count=1,
        gpu_memory_mb=8192,
        timeout_sec=3600,
        parallelism=1,
    )


@pytest.mark.asyncio
async def test_registry_registers_and_lists_active_capability() -> None:
    registry = WorkerCapabilityRegistry(
        cache=MemoryCacheBackend(),
        ttl_seconds=60,
    )

    await registry.register(_capability())
    active = await registry.list_active()

    assert active == [_capability()]


@pytest.mark.asyncio
async def test_registry_heartbeat_refreshes_existing_worker() -> None:
    cache = MemoryCacheBackend()
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)

    await registry.register(_capability())
    assert await registry.heartbeat("gpu-worker-1") is True
    assert await registry.heartbeat("missing-worker") is False
    assert await cache.ttl("worker:capability:gpu-worker-1") > 0


@pytest.mark.asyncio
async def test_registry_heartbeat_does_not_resurrect_worker_removed_after_read() -> None:
    cache = MemoryCacheBackend()
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)
    await registry.register(_capability())

    original_get_json = cache.get_json

    async def get_then_unregister(key):
        payload = await original_get_json(key)
        await cache.delete(key)
        return payload

    cache.get_json = get_then_unregister

    assert await registry.heartbeat("gpu-worker-1") is False
    assert await cache.exists("worker:capability:gpu-worker-1") is False


@pytest.mark.asyncio
async def test_registry_unregister_removes_worker_from_admission_candidates() -> None:
    registry = WorkerCapabilityRegistry(cache=MemoryCacheBackend(), ttl_seconds=60)
    await registry.register(_capability())

    decision = await registry.select_worker(_request())
    assert decision.admitted is True
    assert decision.worker_id == "gpu-worker-1"

    assert await registry.unregister("gpu-worker-1") is True
    decision = await registry.select_worker(_request())
    assert decision.admitted is False
    assert decision.reason == "no_capable_worker"


@pytest.mark.asyncio
async def test_registry_skips_worker_with_exhausted_dynamic_capacity() -> None:
    cache = MemoryCacheBackend()
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)
    busy_worker = _capability("busy-worker")
    available_worker = _capability("available-worker")
    await registry.register(busy_worker)
    await registry.register(available_worker)

    lease_manager = WorkerResourceLeaseManager(cache=cache)
    request = _request()
    await lease_manager.acquire(
        capability=busy_worker,
        request=request,
        lease_id="busy-1",
    )
    await lease_manager.acquire(
        capability=busy_worker,
        request=request,
        lease_id="busy-2",
    )

    decision = await registry.select_available_worker(request)

    assert decision.admitted is True
    assert decision.worker_id == "available-worker"
    assert decision.queue == "queue-available-worker"


@pytest.mark.asyncio
async def test_registry_reserves_first_available_worker_atomically() -> None:
    cache = MemoryCacheBackend()
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)
    busy_worker = _capability("busy-worker")
    available_worker = _capability("available-worker")
    await registry.register(busy_worker)
    await registry.register(available_worker)

    lease_manager = WorkerResourceLeaseManager(cache=cache)
    request = _request()
    await lease_manager.acquire(
        capability=busy_worker,
        request=request,
        lease_id="busy-1",
    )
    await lease_manager.acquire(
        capability=busy_worker,
        request=request,
        lease_id="busy-2",
    )

    decision = await registry.reserve_worker(
        request,
        reservation_id="task-1:attempt-1",
        ttl_seconds=60,
    )

    assert decision.admitted is True
    assert decision.worker_id == "available-worker"
    assert decision.queue == "queue-available-worker"
    assert await lease_manager.current_usage("available-worker") == {
        "cpu": 8.0,
        "memory_gb": 32.0,
        "parallelism": 1,
    }


@pytest.mark.asyncio
async def test_registry_reservation_prefers_less_loaded_worker() -> None:
    cache = MemoryCacheBackend()
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)
    first_worker = _capability("a-worker")
    second_worker = _capability("b-worker")
    await registry.register(first_worker)
    await registry.register(second_worker)

    lease_manager = WorkerResourceLeaseManager(cache=cache)
    await lease_manager.acquire(
        capability=first_worker,
        request=_request(),
        lease_id="running-task:attempt-1",
        lease_phase="running",
    )

    decision = await registry.reserve_worker(
        _request(),
        reservation_id="new-task:attempt-1",
        ttl_seconds=60,
    )

    assert decision.admitted is True
    assert decision.worker_id == "b-worker"
