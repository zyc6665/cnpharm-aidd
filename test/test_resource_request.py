from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.gpu.allocator import AllocationResult
from app.tasks.executors.factory import TaskExecutor
from app.tasks.executors.errors import ResourceAdmissionFailed, TaskExecutionError
from app.tasks.resource_admission import WorkerCapability
from app.tasks.resource_profile import build_task_resource_snapshot


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
