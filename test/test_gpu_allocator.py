"""GPU 分配器行为测试。"""

import logging
from types import SimpleNamespace

import pytest

from app.gpu.allocator import AllocationStrategy, GPUAllocator


class _DetectorWithStats:
    def __init__(self, utilization_percent: float):
        self.utilization_percent = utilization_percent

    def get_gpu_stats(self, gpu_index: int):
        return SimpleNamespace(utilization_percent=self.utilization_percent)


class _FailingDetector:
    def get_gpu_stats(self, gpu_index: int):
        raise RuntimeError("probe failed")


class _LocalDetector:
    def is_available(self):
        return True

    def get_node_info(self):
        return SimpleNamespace(
            hostname="gpu-host",
            gpu_count=2,
            gpus=[
                SimpleNamespace(
                    gpu_index=0,
                    gpu_name="GPU 0",
                    total_memory_mb=24_000,
                    free_memory_mb=8_000,
                ),
                SimpleNamespace(
                    gpu_index=1,
                    gpu_name="GPU 1",
                    total_memory_mb=24_000,
                    free_memory_mb=16_000,
                ),
            ],
        )


class _FailingNodeDetector:
    def is_available(self):
        return True

    def get_node_info(self):
        raise RuntimeError("node probe failed")


@pytest.mark.asyncio
async def test_is_gpu_idle_uses_utilization_threshold():
    allocator = GPUAllocator(db=None, detector=_DetectorWithStats(9.9))

    assert await allocator._is_gpu_idle("local", 0) is True


@pytest.mark.asyncio
async def test_is_gpu_idle_logs_probe_failure(caplog):
    allocator = GPUAllocator(db=None, detector=_FailingDetector())

    with caplog.at_level(logging.WARNING, logger="app.gpu.allocator"):
        assert await allocator._is_gpu_idle("node-a", 1) is False

    assert "Failed to probe GPU idle state for node=node-a gpu=1" in caplog.text


@pytest.mark.asyncio
async def test_round_robin_strategy_allocates_available_gpu():
    allocator = GPUAllocator(db=None, detector=_LocalDetector())

    result = await allocator.allocate(
        task_id="task-round-robin",
        memory_required_mb=4_000,
        strategy=AllocationStrategy.ROUND_ROBIN,
    )

    assert result.success is True
    assert result.gpu_node_id == "local"
    assert result.gpu_index in {0, 1}


@pytest.mark.asyncio
async def test_load_balance_strategy_uses_most_free_memory():
    allocator = GPUAllocator(db=None, detector=_LocalDetector())

    result = await allocator.allocate(
        task_id="task-load-balance",
        memory_required_mb=4_000,
        strategy=AllocationStrategy.LOAD_BALANCE,
    )

    assert result.success is True
    assert result.gpu_node_id == "local"
    assert result.gpu_index == 1


@pytest.mark.asyncio
async def test_allocate_handles_local_node_probe_failure(caplog):
    allocator = GPUAllocator(db=None, detector=_FailingNodeDetector())

    with caplog.at_level(logging.WARNING, logger="app.gpu.allocator"):
        result = await allocator.allocate(
            task_id="task-node-probe-failure",
            memory_required_mb=4_000,
            strategy=AllocationStrategy.LOAD_BALANCE,
        )

    assert result.success is False
    assert result.message == "No GPU nodes available"
    assert "Failed to detect local GPU nodes: node probe failed" in caplog.text
