"""Worker capability registry 测试。"""

import pytest

from app.cache.memory import MemoryCacheBackend
from app.tasks.resource_admission import ResourceAdmissionPolicy, WorkerCapability
from app.tasks.resource_profile import ResourceRequest
from app.tasks.worker_capability_registry import WorkerCapabilityRegistry


def _capability(worker_id: str = "gpu-worker-1") -> WorkerCapability:
    return WorkerCapability(
        worker_id=worker_id,
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

