"""GPU 分配器行为测试。"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.gpu.allocator import AllocationStrategy, GPUAllocator, TaskPriority


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

    def get_gpu_stats(self, gpu_index: int):
        return SimpleNamespace(utilization_percent=0.0)


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
async def test_allocator_uses_owner_token_for_distributed_lock():
    from app.cache.memory import MemoryCacheBackend

    cache = MemoryCacheBackend()
    allocator = GPUAllocator(
        db=None,
        detector=_DetectorWithStats(0.0),
        cache_client=cache,
    )

    assert await allocator._acquire_lock() is True
    owner_token = await cache.get("gpu:alloc:lock")
    assert isinstance(owner_token, str)
    assert owner_token != "1"

    await allocator._release_lock()

    assert await cache.exists("gpu:alloc:lock") is False


@pytest.mark.asyncio
async def test_is_gpu_idle_logs_probe_failure(caplog):
    """本机卡探针失败 → 判为不空闲并告警（避免把故障卡再分出去）。"""
    allocator = GPUAllocator(db=None, detector=_FailingDetector())

    with caplog.at_level(logging.WARNING, logger="app.gpu.allocator"):
        assert await allocator._is_gpu_idle("local", 1) is False

    assert "Failed to probe GPU idle state for node=local gpu=1" in caplog.text


@pytest.mark.asyncio
async def test_is_gpu_idle_does_not_probe_remote_slot_nodes(caplog):
    """远程卡位/节点的卡由 Agent 观测上报，平台侧不探针（否则多节点下全部判忙）。"""
    allocator = GPUAllocator(db=None, detector=_FailingDetector())

    with caplog.at_level(logging.WARNING, logger="app.gpu.allocator"):
        assert await allocator._is_gpu_idle("dcu-node-a", 1) is True

    assert "Failed to probe GPU idle state" not in caplog.text


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
async def test_memory_fit_skips_busy_gpu():
    allocator = GPUAllocator(db=None, detector=_LocalDetector())
    allocator._is_gpu_idle = AsyncMock(side_effect=[False, True])

    result = await allocator._try_allocate_by_memory(
        [
            {
                "id": "local",
                "gpus": [
                    {"index": 0, "free_memory_mb": 6_000},
                    {"index": 1, "free_memory_mb": 16_000},
                ],
            }
        ],
        task_id="task-memory-fit",
        memory_required_mb=4_000,
    )

    assert result is not None
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


@pytest.mark.asyncio
async def test_high_priority_preemption_skip_uses_debug_log(caplog):
    allocator = GPUAllocator(db=None, detector=_LocalDetector())

    with caplog.at_level(logging.DEBUG, logger="app.gpu.allocator"):
        result = await allocator.allocate(
            task_id="task-preempt",
            memory_required_mb=99_999,
            priority=TaskPriority.HIGH,
            strategy=AllocationStrategy.LOAD_BALANCE,
        )

    assert result.success is False
    assert result.wait_position == 1
    assert "GPU preemption skipped for task=task-preempt" in caplog.text


@pytest.mark.asyncio
async def test_create_allocation_persists_task_gpu_fields():
    db = AsyncMock()
    allocator = GPUAllocator(db=db, detector=_LocalDetector())

    result = await allocator._create_allocation(
        task_id="task-persist",
        node_id="node-1",
        gpu_index=0,
        memory_mb=4096,
    )

    assert result.success is True
    db.execute.assert_awaited_once()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_clears_persisted_task_gpu_fields():
    db = AsyncMock()
    allocator = GPUAllocator(db=db, detector=_LocalDetector())

    assert await allocator.release(task_id="task-persist") is True

    db.execute.assert_awaited_once()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_is_gpu_idle_rejects_persisted_active_task():
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: "task-active")
    allocator = GPUAllocator(db=db, detector=_DetectorWithStats(0.0))

    assert await allocator._is_gpu_idle("node-1", 0) is False
