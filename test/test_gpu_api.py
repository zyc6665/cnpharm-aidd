"""GPU资源接口回归测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1 import gpu
from app.api.v1 import api_router
from app.auth.dependencies import get_admin_user


def test_gpu_router_is_registered_in_v1_api() -> None:
    """GPU接口应暴露在统一的v1路由下。"""
    paths = {route.path for route in api_router.routes}

    assert "/gpu/info" in paths
    assert "/gpu/allocate" in paths
    assert "/gpu/release" in paths


def test_gpu_mutation_routes_require_admin() -> None:
    """手动分配和释放属于后台资源操作，只允许管理员调用。"""
    dependencies = {
        route.path: {dependency.call for dependency in route.dependant.dependencies}
        for route in gpu.router.routes
        if route.path in {"/gpu/allocate", "/gpu/release"}
    }

    assert get_admin_user in dependencies["/gpu/allocate"]
    assert get_admin_user in dependencies["/gpu/release"]


@pytest.mark.asyncio
async def test_allocate_gpu_uses_database_session(monkeypatch) -> None:
    """分配接口应把请求会话传入分配器并提交持久化。"""
    db = AsyncMock()
    expected = gpu.AllocationResponse(
        success=True,
        gpu_node_id="local",
        gpu_index=0,
        allocated_memory_mb=2048,
        allocation_id="allocation-1",
        message="ok",
    )

    class FakeAllocator:
        def __init__(self, *, db):
            assert db is not None

        async def allocate(self, **kwargs):
            assert kwargs == {
                "task_id": "task-1",
                "memory_required_mb": 2048,
                "priority": gpu.TaskPriority.NORMAL,
            }
            return SimpleNamespace(**expected.model_dump())

    monkeypatch.setattr(gpu, "GPUAllocator", FakeAllocator)

    result = await gpu.allocate_gpu(
        gpu.AllocationRequest(task_id="task-1", memory_required_mb=2048),
        admin_user=object(),
        db=db,
    )

    assert result["code"] == 200
    assert result["data"] == expected.model_dump()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_gpu_uses_database_session(monkeypatch) -> None:
    """释放接口应使用数据库会话清除任务占用。"""
    db = AsyncMock()
    observed = {}

    class FakeAllocator:
        def __init__(self, *, db):
            observed["session"] = db

        async def release(self, **kwargs):
            observed["kwargs"] = kwargs
            return True

    monkeypatch.setattr(gpu, "GPUAllocator", FakeAllocator)

    result = await gpu.release_gpu(
        gpu.ReleaseRequest(task_id="task-1", allocation_id="allocation-1"),
        admin_user=object(),
        db=db,
    )

    assert result["code"] == 200
    assert result["message"] == "GPU released successfully"
    assert result["data"] is None
    assert observed == {
        "session": db,
        "kwargs": {"task_id": "task-1", "allocation_id": "allocation-1"},
    }
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_gpu_stats_returns_standard_envelope(monkeypatch) -> None:
    """GPU 统计列表必须走统一响应信封，避免前端拿到裸数组。"""
    stat = SimpleNamespace(
        gpu_index=0,
        utilization_percent=42.0,
        memory_used_mb=1024,
        memory_free_mb=2048,
        memory_total_mb=3072,
        temperature_celsius=55.0,
        power_watts=120.0,
        fan_speed_percent=40.0,
    )

    class FakeDetector:
        def is_available(self):
            return True

        def get_all_gpu_stats(self):
            return [stat]

    monkeypatch.setattr(gpu, "get_gpu_detector", lambda: FakeDetector())

    result = await gpu.get_gpu_stats(current_user=object())

    assert result["code"] == 200
    assert isinstance(result["data"], list)
    first = result["data"][0]
    assert first.gpu_index == 0
    assert first.utilization_percent == 42.0
