from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.gpu.allocator import AllocationResult
from app.tasks.executors.factory import TaskExecutor
from app.tasks.executors.errors import ResourceAdmissionFailed, TaskExecutionError
from app.tasks.resource_admission import WorkerCapability
from app.tasks.resource_lease import WorkerResourceLeaseManager
from app.tasks.resource_profile import (
    build_task_resource_snapshot,
    resource_request_from_snapshot,
)
from app.cache.memory import MemoryCacheBackend


def test_build_task_resource_snapshot_emits_canonical_resource_request() -> None:
    snapshot = build_task_resource_snapshot(
        {
            "type": "docker_image",
            "timeout_sec": 7200,
            "resource_profile": {
                "tier": "heavy",
                "cpu": 16,
                "memory_gb": 64,
                "gpu_required": True,
                "gpu_memory_gb": 16,
                "expected_minutes": 240,
                "parallelism": 1,
            },
        },
        gpu_required=True,
        gpu_memory_mb=16384,
    )

    assert snapshot["resource_request"] == {
        "executor_type": "docker_image",
        "tier": "heavy",
        "cpu": 16.0,
        "memory_gb": 64.0,
        "cpu_limit": 16.0,
        "memory_limit": "64g",
        "gpu_required": True,
        "gpu_count": 1,
        "gpu_memory_mb": 16384,
        "timeout_sec": 7200,
        "parallelism": 1,
    }


def test_task_executor_hydrates_cpu_and_memory_limits_from_resource_snapshot() -> None:
    task = SimpleNamespace(
        id="task-resource",
        extra_data={
            "resource_snapshot": build_task_resource_snapshot(
                {
                    "type": "docker_image",
                    "resource_profile": {
                        "tier": "heavy",
                        "cpu": 8,
                        "memory_gb": 32,
                        "parallelism": 1,
                    },
                }
            )
        },
    )
    tool_version = SimpleNamespace(config={"type": "docker_image"})

    executor = TaskExecutor(task, tool_version)

    assert executor.config["cpu_limit"] == 8.0
    assert executor.config["memory_limit"] == "32g"
    assert executor.config["parallelism"] == 1


def test_task_executor_rejects_request_that_worker_capability_cannot_admit() -> None:
    task = SimpleNamespace(
        id="task-admission",
        extra_data={
            "resource_snapshot": build_task_resource_snapshot(
                {
                    "type": "docker_image",
                    "gpu_required": True,
                    "gpu_memory_mb": 16384,
                }
            )
        },
    )
    executor = TaskExecutor(
        task,
        SimpleNamespace(config={"type": "docker_image"}),
        worker_capability=WorkerCapability(
            worker_id="gpu-worker-1",
            executor_types=("docker_image",),
            gpu_count=1,
            gpu_memory_mb=8192,
        ),
    )

    with pytest.raises(ResourceAdmissionFailed, match="资源准入失败"):
        executor._admit_resources()


@pytest.mark.asyncio
async def test_task_executor_acquires_and_releases_dynamic_resource_lease() -> None:
    cache = MemoryCacheBackend()
    task = SimpleNamespace(
        id="task-dynamic-resource",
        extra_data={
            "resource_snapshot": build_task_resource_snapshot(
                {
                    "type": "docker_image",
                    "resource_profile": {
                        "tier": "heavy",
                        "cpu": 4,
                        "memory_gb": 8,
                        "parallelism": 1,
                    },
                }
            )
        },
    )
    executor = TaskExecutor(
        task,
        SimpleNamespace(config={"type": "docker_image"}),
        cache_client=cache,
        worker_capability=WorkerCapability(
            worker_id="cpu-worker-1",
            cpu_capacity=8,
            memory_capacity_gb=16,
            parallelism=2,
        ),
    )

    await executor._acquire_resources()
    assert executor._resource_lease_heartbeat_task is not None
    usage = await WorkerResourceLeaseManager(cache=cache).current_usage("cpu-worker-1")
    assert usage == {"cpu": 4.0, "memory_gb": 8.0, "parallelism": 1}

    await executor._release_resource_lease()
    assert executor._resource_lease_heartbeat_task is None
    usage = await WorkerResourceLeaseManager(cache=cache).current_usage("cpu-worker-1")
    assert usage == {"cpu": 0.0, "memory_gb": 0.0, "parallelism": 0}


@pytest.mark.asyncio
async def test_task_executor_stops_when_resource_lease_heartbeat_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = MemoryCacheBackend()
    task = SimpleNamespace(
        id="task-lease-heartbeat-failure",
        extra_data={
            "resource_snapshot": build_task_resource_snapshot(
                {
                    "type": "docker_image",
                    "resource_profile": {"cpu": 4, "memory_gb": 8, "parallelism": 1},
                }
            )
        },
    )
    executor = TaskExecutor(
        task,
        SimpleNamespace(config={"type": "docker_image"}),
        cache_client=cache,
        worker_capability=WorkerCapability(
            worker_id="cpu-worker-1",
            cpu_capacity=8,
            memory_capacity_gb=16,
            parallelism=2,
        ),
    )

    await executor._acquire_resources()

    async def fail_sleep(_seconds: float) -> None:
        return None

    async def fail_heartbeat(**kwargs) -> bool:
        raise RuntimeError("cache unavailable")

    monkeypatch.setattr("app.tasks.executors.factory.asyncio.sleep", fail_sleep)
    executor._resource_lease_manager.heartbeat = fail_heartbeat

    await executor._resource_lease_heartbeat_loop()

    assert executor._resource_lease_lost is True
    await executor._release_resource_lease()


@pytest.mark.asyncio
async def test_task_executor_reuses_dispatch_reservation_without_double_counting() -> None:
    cache = MemoryCacheBackend()
    capability = WorkerCapability(
        worker_id="cpu-worker-1",
        cpu_capacity=8,
        memory_capacity_gb=16,
        parallelism=2,
    )
    snapshot = build_task_resource_snapshot(
        {
            "type": "docker_image",
            "resource_profile": {
                "tier": "heavy",
                "cpu": 4,
                "memory_gb": 8,
                "parallelism": 1,
            },
        }
    )
    task = SimpleNamespace(
        id="task-reserved-resource",
        extra_data={
            "execution_attempt_id": "attempt-1",
            "dispatch": {
                "resource_reservation": {
                    "worker_id": "cpu-worker-1",
                    "lease_id": "task-reserved-resource:attempt-1",
                    "ttl_seconds": 60,
                    "status": "reserved",
                }
            },
            "resource_snapshot": snapshot,
        },
    )
    request = resource_request_from_snapshot(
        {"type": "docker_image"},
        snapshot,
    )
    manager = WorkerResourceLeaseManager(cache=cache)
    reservation = await manager.acquire(
        capability=capability,
        request=request,
        lease_id="task-reserved-resource:attempt-1",
        ttl_seconds=60,
    )
    assert reservation.acquired is True

    executor = TaskExecutor(
        task,
        SimpleNamespace(config={"type": "docker_image"}),
        cache_client=cache,
        worker_capability=capability,
    )

    await executor._acquire_resources()

    assert await manager.current_usage(capability.worker_id) == {
        "cpu": 4.0,
        "memory_gb": 8.0,
        "parallelism": 1,
    }
    assert task.extra_data["dispatch"]["resource_reservation"]["status"] == "claimed"
    await executor._release_resource_lease()
    assert await manager.current_usage(capability.worker_id) == {
        "cpu": 0.0,
        "memory_gb": 0.0,
        "parallelism": 0,
    }


@pytest.mark.asyncio
async def test_task_executor_rejects_dispatch_reservation_on_wrong_worker() -> None:
    task = SimpleNamespace(
        id="task-reserved-wrong-worker",
        extra_data={
            "execution_attempt_id": "attempt-1",
            "resource_snapshot": build_task_resource_snapshot(
                {"type": "docker_image", "resource_profile": {"cpu": 1}}
            ),
            "dispatch": {
                "resource_reservation": {
                    "worker_id": "worker-target",
                    "lease_id": "task-reserved-wrong-worker:attempt-1",
                    "status": "reserved",
                }
            },
        },
    )
    executor = TaskExecutor(
        task,
        SimpleNamespace(config={"type": "docker_image"}),
        cache_client=MemoryCacheBackend(),
        worker_capability=WorkerCapability(worker_id="worker-other", cpu_capacity=4),
    )

    with pytest.raises(ResourceAdmissionFailed, match="非目标 Worker"):
        await executor._acquire_resources()


@pytest.mark.asyncio
async def test_task_executor_rejects_when_dynamic_capacity_is_exhausted() -> None:
    cache = MemoryCacheBackend()
    capability = WorkerCapability(
        worker_id="cpu-worker-1",
        cpu_capacity=4,
        parallelism=1,
    )
    snapshot = build_task_resource_snapshot(
        {
            "type": "docker_image",
            "resource_profile": {"tier": "heavy", "cpu": 4},
        }
    )
    first = TaskExecutor(
        SimpleNamespace(id="task-dynamic-1", extra_data={"resource_snapshot": snapshot}),
        SimpleNamespace(config={"type": "docker_image"}),
        cache_client=cache,
        worker_capability=capability,
    )
    second = TaskExecutor(
        SimpleNamespace(id="task-dynamic-2", extra_data={"resource_snapshot": snapshot}),
        SimpleNamespace(config={"type": "docker_image"}),
        cache_client=cache,
        worker_capability=capability,
    )

    await first._acquire_resources()
    with pytest.raises(ResourceAdmissionFailed, match="资源动态占用失败"):
        await second._acquire_resources()
    await first._release_resource_lease()


@pytest.mark.asyncio
async def test_task_executor_binds_allocated_gpu_device_to_runtime_config() -> None:
    task = SimpleNamespace(
        id="task-gpu-resource",
        extra_data={
            "resource_snapshot": build_task_resource_snapshot(
                {
                    "type": "docker_image",
                    "gpu_required": True,
                    "gpu_memory_mb": 4096,
                }
            )
        },
        gpu_node_id=None,
        gpu_index=None,
        gpu_memory_allocated_mb=None,
    )
    allocator = AsyncMock()
    allocator.allocate.return_value = AllocationResult(
        success=True,
        gpu_node_id="node-1",
        gpu_index=2,
        allocated_memory_mb=4096,
        allocation_id="allocation-1",
    )

    with patch("app.gpu.allocator.GPUAllocator", return_value=allocator):
        executor = TaskExecutor(
            task,
            SimpleNamespace(config={"type": "docker_image", "gpu_required": True}),
        )
        await executor._allocate_gpu()

    assert executor.config["gpu_config"]["count"] == 1
    assert executor.config["gpu_config"]["device"] == "2"
