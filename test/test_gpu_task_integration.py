"""GPU 分配器与任务执行器集成测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tasks.executor import (  # noqa: E402
    TaskExecutor,
    TaskExecutionError,
    GPUAllocationFailed,
)
from app.models.tasks import Task, TaskStatus  # noqa: E402
from app.gpu.allocator import AllocationResult  # noqa: E402
from app.tasks.state_machine import TaskStateMachine  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────


def _make_task(**overrides) -> Task:
    """创建测试 Task 实例，默认 GPU 相关字段为空。"""
    defaults = dict(
        id="task-001",
        status=TaskStatus.PENDING.value,
        tool_id="tool-1",
        tool_version_id="tv-1",
        retry_count=0,
        max_retries=3,
        gpu_node_id=None,
        gpu_index=None,
        gpu_memory_allocated_mb=None,
        user_id="user-1",
    )
    defaults.update(overrides)
    return Task(**defaults)


def _make_config(**overrides) -> dict:
    """创建最小工具版本配置 dict。"""
    cfg = {"type": "docker_image", "image": "test:latest"}
    cfg.update(overrides)
    return cfg


def _make_allocator_mock(*, success: bool = True, message: str = "OK"):
    """创建 GPUAllocator mock。"""
    allocator = AsyncMock()
    allocator.allocate.return_value = AllocationResult(
        success=success,
        gpu_node_id="node-1" if success else None,
        gpu_index=0 if success else None,
        allocated_memory_mb=4096 if success else 0,
        allocation_id="alloc-1" if success else None,
        message=message,
    )
    allocator.release.return_value = True
    return allocator


# ── context mananger: enable execute_with_progress for mock tasks ───────


from contextlib import ExitStack, contextmanager


@contextmanager
def _patch_sm_for_ewp():
    """为 execute_with_progress mock 必要的状态机方法。

    - update_progress: mock 为 no-op（mock task 在 RUNNING 前的 progress 调用会失败）
    - start: mock 为实际执行 PENDING→RUNNING 转换的 side_effect
    - transition / complete: 保持真实实现以验证 GPU 重试逻辑
    """
    def _do_start(task, progress_message=None):
        TaskStateMachine.transition(task, TaskStatus.RUNNING, progress_message=progress_message)

    with ExitStack() as stack:
        stack.enter_context(patch.object(TaskStateMachine, "update_progress"))
        stack.enter_context(patch.object(
            TaskStateMachine, "start",
            side_effect=_do_start,
        ))
        yield


# =========================================================================
#  Tests
# =========================================================================


class TestGPUAllocation:
    """_allocate_gpu 单元测试。"""

    def test_uses_tool_gpu_settings_over_version_config(self):
        task = _make_task()
        tool = SimpleNamespace(gpu_required=True, gpu_memory_mb=8192)
        executor = TaskExecutor(
            task,
            SimpleNamespace(config=_make_config(gpu_required=False)),
            tool=tool,
        )

        assert executor.config["gpu_required"] is True
        assert executor.config["gpu_memory_required_mb"] == 8192

    def test_uses_task_resource_snapshot_over_mutated_tool_settings(self):
        task = _make_task(
            extra_data={
                "resource_snapshot": {
                    "executor_type": "docker_image",
                    "gpu_required": True,
                    "gpu_memory_mb": 16384,
                    "timeout_sec": 3600,
                    "resource_profile": {"tier": "heavy"},
                }
            }
        )
        tool = SimpleNamespace(gpu_required=False, gpu_memory_mb=0)
        executor = TaskExecutor(
            task,
            SimpleNamespace(
                config=_make_config(
                    gpu_required=False,
                    gpu_memory_required_mb=1024,
                    timeout_sec=30,
                )
            ),
            tool=tool,
        )

        assert executor.config["gpu_required"] is True
        assert executor.config["gpu_memory_required_mb"] == 16384
        assert executor.config["timeout_sec"] == 3600

    @pytest.mark.asyncio
    async def test_skips_when_gpu_not_required(self):
        task = _make_task()
        executor = TaskExecutor(task, SimpleNamespace(config=_make_config()))
        result = await executor._allocate_gpu()
        assert result is None

    @pytest.mark.asyncio
    async def test_allocates_when_gpu_required_and_succeeds(self):
        task = _make_task()
        cfg = _make_config(gpu_required=True, gpu_memory_required_mb=8192)
        alloc = _make_allocator_mock()

        with patch("app.gpu.allocator.GPUAllocator", return_value=alloc):
            executor = TaskExecutor(task, SimpleNamespace(config=cfg))
            result = await executor._allocate_gpu()

        assert result is not None
        assert result["node_id"] == "node-1"
        assert result["gpu_index"] == 0
        assert result["memory_mb"] == 4096
        assert task.gpu_node_id == "node-1"
        assert task.gpu_index == 0
        assert task.gpu_memory_allocated_mb == 4096
        alloc.allocate.assert_called_once_with(
            task_id="task-001",
            memory_required_mb=8192,
        )

    @pytest.mark.asyncio
    async def test_raises_on_allocation_failure(self):
        task = _make_task()
        cfg = _make_config(gpu_required=True)
        alloc = _make_allocator_mock(success=False, message="No GPU nodes")

        with patch("app.gpu.allocator.GPUAllocator", return_value=alloc):
            executor = TaskExecutor(task, SimpleNamespace(config=cfg))
            with pytest.raises(GPUAllocationFailed, match="No GPU nodes"):
                await executor._allocate_gpu()

    @pytest.mark.asyncio
    async def test_uses_default_memory_4096(self):
        task = _make_task()
        cfg = _make_config(gpu_required=True)  # 无 gpu_memory_required_mb
        alloc = _make_allocator_mock()

        with patch("app.gpu.allocator.GPUAllocator", return_value=alloc):
            executor = TaskExecutor(task, SimpleNamespace(config=cfg))
            await executor._allocate_gpu()

        alloc.allocate.assert_called_once_with(
            task_id="task-001",
            memory_required_mb=4096,
        )


class TestGPURelease:
    """_release_gpu 单元测试。"""

    @pytest.mark.asyncio
    async def test_skips_when_no_gpu_allocated(self):
        task = _make_task(gpu_node_id=None)
        executor = TaskExecutor(task, SimpleNamespace(config=_make_config()))
        await executor._release_gpu()  # no-op, 无异常

    @pytest.mark.asyncio
    async def test_releases_and_clears_fields(self):
        task = _make_task(gpu_node_id="node-1", gpu_index=0, gpu_memory_allocated_mb=4096)
        alloc = _make_allocator_mock()

        with patch("app.gpu.allocator.GPUAllocator", return_value=alloc):
            executor = TaskExecutor(task, SimpleNamespace(config=_make_config()))
            await executor._release_gpu()

        alloc.release.assert_called_once_with(task_id="task-001")
        assert task.gpu_node_id is None
        assert task.gpu_index is None
        assert task.gpu_memory_allocated_mb is None


class TestExecuteWithProgressGPU:
    """execute_with_progress GPU 重试 / 释放集成测试。"""

    @pytest.mark.asyncio
    async def test_starts_before_reporting_initial_progress(self):
        """兼容入口应先进入 RUNNING，再写入初始进度。"""
        task = _make_task()
        inner = AsyncMock()
        inner.execute.return_value = {"success": True}

        with patch.object(TaskExecutor, "_get_executor", return_value=inner) as get_executor:
            executor = TaskExecutor(task, SimpleNamespace(config=_make_config()))
            result = await executor.execute_with_progress()

        assert result == {"success": True}
        assert task.status == TaskStatus.SUCCESS.value
        get_executor.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_reenqueues_on_gpu_failure_within_retry_limit(self):
        """分配失败 + 未达最大重试 → PENDING 重新入队。"""
        task = _make_task(retry_count=0, max_retries=3)
        cfg = _make_config(gpu_required=True)
        alloc = _make_allocator_mock(success=False, message="No GPU")

        with patch("app.gpu.allocator.GPUAllocator", return_value=alloc):
            with _patch_sm_for_ewp():
                executor = TaskExecutor(task, SimpleNamespace(config=cfg))
                with pytest.raises(GPUAllocationFailed):
                    await executor.execute_with_progress()

        assert task.status == TaskStatus.PENDING.value
        assert task.retry_count == 1
        assert "GPU分配失败" in (task.progress_message or "")

    @pytest.mark.asyncio
    async def test_gpu_retry_uses_defaults_before_task_flush(self):
        task = _make_task(retry_count=None, max_retries=None)
        cfg = _make_config(gpu_required=True)
        alloc = _make_allocator_mock(success=False, message="No GPU")

        with patch("app.gpu.allocator.GPUAllocator", return_value=alloc):
            with _patch_sm_for_ewp():
                executor = TaskExecutor(task, SimpleNamespace(config=cfg))
                with pytest.raises(GPUAllocationFailed):
                    await executor.execute_with_progress()

        assert task.status == TaskStatus.PENDING.value
        assert task.retry_count == 1

    @pytest.mark.asyncio
    async def test_fails_on_gpu_failure_exceeding_retry_limit(self):
        """分配失败 + 已达最大重试 → FAILURE。"""
        task = _make_task(retry_count=3, max_retries=3)
        cfg = _make_config(gpu_required=True)
        alloc = _make_allocator_mock(success=False, message="No GPU")

        with patch("app.gpu.allocator.GPUAllocator", return_value=alloc):
            with _patch_sm_for_ewp():
                executor = TaskExecutor(task, SimpleNamespace(config=cfg))
                with pytest.raises(GPUAllocationFailed):
                    await executor.execute_with_progress()

        assert task.status == TaskStatus.FAILURE.value
        assert "GPU分配失败" in (task.error_message or "")

    @pytest.mark.asyncio
    async def test_releases_gpu_after_success(self):
        """执行成功 → GPU 释放。"""
        task = _make_task()
        cfg = _make_config(gpu_required=True)
        alloc = _make_allocator_mock()
        inner = AsyncMock()
        inner.execute.return_value = {"success": True}

        with patch("app.gpu.allocator.GPUAllocator", return_value=alloc):
            with _patch_sm_for_ewp():
                with patch.object(TaskExecutor, "_get_executor", return_value=inner):
                    executor = TaskExecutor(task, SimpleNamespace(config=cfg))
                    result = await executor.execute_with_progress()

        assert result == {"success": True}
        assert task.status == TaskStatus.SUCCESS.value
        alloc.release.assert_called_once_with(task_id="task-001", allocation_id="alloc-1")
        assert task.gpu_node_id is None

    @pytest.mark.asyncio
    async def test_releases_gpu_after_execution_error(self):
        """执行失败 → finally 中仍释放 GPU。"""
        task = _make_task()
        cfg = _make_config(gpu_required=True)
        alloc = _make_allocator_mock()
        inner = AsyncMock()
        inner.execute.side_effect = TaskExecutionError("simulated failure")

        with patch("app.gpu.allocator.GPUAllocator", return_value=alloc):
            with _patch_sm_for_ewp():
                with patch.object(TaskExecutor, "_get_executor", return_value=inner):
                    executor = TaskExecutor(task, SimpleNamespace(config=cfg))
                    with pytest.raises(TaskExecutionError):
                        await executor.execute_with_progress()

        alloc.release.assert_called_once_with(task_id="task-001", allocation_id="alloc-1")
        assert task.gpu_node_id is None

    @pytest.mark.asyncio
    async def test_skips_gpu_when_not_required(self):
        """无 GPU 需求时正常执行，不报错。"""
        task = _make_task()
        inner = AsyncMock()
        inner.execute.return_value = {"success": True}

        with _patch_sm_for_ewp():
            with patch.object(TaskExecutor, "_get_executor", return_value=inner):
                executor = TaskExecutor(task, SimpleNamespace(config=_make_config()))
                result = await executor.execute_with_progress()

        assert result == {"success": True}
        assert task.status == TaskStatus.SUCCESS.value


class TestExecuteGPU:
    """execute() 方法的 GPU 集成测试。"""

    @pytest.mark.asyncio
    async def test_allocates_and_releases_gpu(self):
        task = _make_task()
        cfg = _make_config(gpu_required=True)
        alloc = _make_allocator_mock()
        inner = AsyncMock()
        inner.execute.return_value = {"success": True}

        with patch("app.gpu.allocator.GPUAllocator", return_value=alloc):
            with patch.object(TaskExecutor, "_get_executor", return_value=inner):
                executor = TaskExecutor(task, SimpleNamespace(config=cfg))
                result = await executor.execute()

        assert result == {"success": True}
        alloc.allocate.assert_called_once()
        alloc.release.assert_called_once()
        assert task.gpu_node_id is None

    @pytest.mark.asyncio
    async def test_raises_on_allocation_failure(self):
        task = _make_task()
        cfg = _make_config(gpu_required=True)
        alloc = _make_allocator_mock(success=False, message="No GPU")

        with patch("app.gpu.allocator.GPUAllocator", return_value=alloc):
            executor = TaskExecutor(task, SimpleNamespace(config=cfg))
            with pytest.raises(GPUAllocationFailed, match="No GPU"):
                await executor.execute()


class TestGPUAllocationFailedException:
    """GPUAllocationFailed 异常自身。"""

    def test_is_task_execution_error_subclass(self):
        exc = GPUAllocationFailed("test")
        assert isinstance(exc, TaskExecutionError)

    def test_stores_wait_position(self):
        exc = GPUAllocationFailed("test", wait_position=5)
        assert exc.wait_position == 5
        assert exc.details["wait_position"] == 5

    def test_no_wait_position_default(self):
        exc = GPUAllocationFailed("test")
        assert exc.wait_position is None
        assert exc.details["wait_position"] is None
