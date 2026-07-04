"""GPU 分配器行为测试。"""

import logging
from types import SimpleNamespace

import pytest

from app.gpu.allocator import GPUAllocator


class _DetectorWithStats:
    def __init__(self, utilization_percent: float):
        self.utilization_percent = utilization_percent

    def get_gpu_stats(self, gpu_index: int):
        return SimpleNamespace(utilization_percent=self.utilization_percent)


class _FailingDetector:
    def get_gpu_stats(self, gpu_index: int):
        raise RuntimeError("probe failed")


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
