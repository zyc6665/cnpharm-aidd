"""任务执行器工厂与 GPU 生命周期编排。"""

import logging
import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from app.models.tasks import TaskStatus
from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.errors import GPUAllocationFailed, TaskExecutionError
from app.tasks.attempts import get_execution_attempt_id
from app.tasks.executors.resolver import ExecutorResolver
from app.tasks.state_machine import DEFAULT_MAX_RETRIES, TaskStateMachine

if TYPE_CHECKING:
    from app.models.tasks import Task
    from app.models.tools import ToolVersion

logger = logging.getLogger(__name__)

def supported_executor_types() -> tuple[str, ...]:
    """返回 V1 Executor Gateway 已登记的执行器类型。"""
    return ExecutorResolver().supported_types()


class TaskExecutor:
    """按工具类型选择执行器并管理 GPU 生命周期。"""

    def __init__(
        self,
        task: "Task",
        tool_version: "ToolVersion",
        tool: Optional[Any] = None,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
        executor_resolver: ExecutorResolver | None = None,
    ):
        self.task = task
        self.tool_version = tool_version
        self.progress_callback = progress_callback
        self.executor_resolver = executor_resolver or ExecutorResolver()
        self._allocation_id: str | None = None
        self._gpu_heartbeat_task: asyncio.Task[None] | None = None
        self.config = dict(tool_version.config or {})
        resource_snapshot = (
            task.extra_data.get("resource_snapshot")
            if isinstance(getattr(task, "extra_data", None), dict)
            else None
        )
        if isinstance(resource_snapshot, dict):
            if "gpu_required" in resource_snapshot:
                self.config["gpu_required"] = bool(resource_snapshot["gpu_required"])
            if "gpu_memory_mb" in resource_snapshot:
                self.config["gpu_memory_required_mb"] = int(
                    resource_snapshot["gpu_memory_mb"] or 0
                )
            if resource_snapshot.get("timeout_sec"):
                self.config["timeout_sec"] = int(resource_snapshot["timeout_sec"])
        if tool is not None:
            if not isinstance(resource_snapshot, dict):
                self.config["gpu_required"] = bool(tool.gpu_required)
                if tool.gpu_required:
                    self.config["gpu_memory_required_mb"] = int(tool.gpu_memory_mb or 4096)

    def _get_executor(self) -> BaseExecutor:
        executor_type = str(self.config.get("type") or "")
        executor_class = self.executor_resolver.resolve(executor_type)
        return executor_class(
            self.task,
            self.tool_version,
            config=self.config,
            progress_callback=self.progress_callback,
        )

    async def _allocate_gpu(self) -> Optional[dict[str, Any]]:
        if not self.config.get("gpu_required", False):
            return None
        from app.database.session import get_async_session
        from app.gpu.allocator import GPUAllocator

        async for session in get_async_session():
            try:
                allocation_kwargs = {
                    "task_id": str(self.task.id),
                    "memory_required_mb": self.config.get("gpu_memory_required_mb", 4096),
                }
                attempt_id = get_execution_attempt_id(self.task)
                if attempt_id is not None:
                    allocation_kwargs["attempt_id"] = attempt_id
                result = await GPUAllocator(session).allocate(**allocation_kwargs)
                if not result.success:
                    raise GPUAllocationFailed(
                        result.message or "No GPU resources available",
                        wait_position=result.wait_position,
                    )
                self._allocation_id = result.allocation_id
                self.task.gpu_node_id, self.task.gpu_index = result.gpu_node_id, result.gpu_index
                self.task.gpu_memory_allocated_mb = result.allocated_memory_mb
                await session.commit()
                self._start_gpu_heartbeat()
                return {
                    "allocation_id": result.allocation_id,
                    "node_id": result.gpu_node_id,
                    "gpu_index": result.gpu_index,
                    "memory_mb": result.allocated_memory_mb,
                }
            except GPUAllocationFailed:
                raise
            except Exception as exc:
                await session.rollback()
                raise TaskExecutionError(f"GPU allocation unexpected error: {exc}") from exc

    async def _release_gpu(self) -> None:
        await self._stop_gpu_heartbeat()
        if not self.task.gpu_node_id:
            return
        from app.database.session import get_async_session
        from app.gpu.allocator import GPUAllocator

        async for session in get_async_session():
            try:
                release_kwargs = {"task_id": str(self.task.id)}
                if self._allocation_id is not None:
                    release_kwargs["allocation_id"] = self._allocation_id
                await GPUAllocator(session).release(**release_kwargs)
                self.task.gpu_node_id = None
                self.task.gpu_index = None
                self.task.gpu_memory_allocated_mb = None
                await session.commit()
            except Exception as exc:
                logger.warning("Failed to release GPU allocation for task %s: %s", self.task.id, exc)

    def _start_gpu_heartbeat(self) -> None:
        if self._allocation_id is None or self._gpu_heartbeat_task is not None:
            return
        self._gpu_heartbeat_task = asyncio.create_task(self._gpu_heartbeat_loop())

    async def _stop_gpu_heartbeat(self) -> None:
        heartbeat_task = self._gpu_heartbeat_task
        self._gpu_heartbeat_task = None
        if heartbeat_task is None:
            return
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task

    async def _gpu_heartbeat_loop(self) -> None:
        from app.gpu.allocator import (
            GPUAllocator,
            GPU_LEASE_HEARTBEAT_INTERVAL_SECONDS,
        )

        while True:
            await asyncio.sleep(GPU_LEASE_HEARTBEAT_INTERVAL_SECONDS)
            if self._allocation_id is None:
                return

            from app.database.session import get_async_session

            async for session in get_async_session():
                try:
                    await GPUAllocator(session).heartbeat(
                        task_id=str(self.task.id),
                        allocation_id=self._allocation_id,
                    )
                    await session.commit()
                except Exception as exc:
                    await session.rollback()
                    logger.warning(
                        "Failed to heartbeat GPU allocation for task %s: %s",
                        self.task.id,
                        exc,
                    )

    async def execute(self) -> dict[str, Any]:
        executor = self._get_executor()
        try:
            await self._allocate_gpu()
            return await executor.execute()
        except (GPUAllocationFailed, TaskExecutionError):
            raise
        except Exception as exc:
            logger.exception("Task %s unexpected error", self.task.id)
            raise TaskExecutionError(f"Unexpected error: {exc}") from exc
        finally:
            await self._release_gpu()

    async def execute_with_progress(
        self,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> dict[str, Any]:
        async def report(progress: float, message: str) -> None:
            TaskStateMachine.update_progress(self.task, progress, message)
            if progress_callback:
                await progress_callback(progress, message)

        try:
            TaskStateMachine.start(self.task)
            await report(0, "任务准备中")
            executor = self._get_executor()
            try:
                await self._allocate_gpu()
            except GPUAllocationFailed as exc:
                retry_count = self.task.retry_count if self.task.retry_count is not None else 0
                max_retries = (
                    self.task.max_retries
                    if self.task.max_retries is not None
                    else DEFAULT_MAX_RETRIES
                )
                if retry_count < max_retries:
                    TaskStateMachine.transition(
                        self.task,
                        TaskStatus.PENDING,
                        progress_message=(
                            f"GPU分配失败: {exc.message}，"
                            f"重试 {retry_count}/{max_retries}"
                        ),
                    )
                else:
                    TaskStateMachine.complete(
                        self.task,
                        success=False,
                        error_message=(
                            f"GPU分配失败(已达最大重试 {max_retries}): "
                            f"{exc.message}"
                        ),
                    )
                raise
            await report(10, "任务开始执行")
            result = await executor.execute()
            await report(100, "任务执行完成")
            TaskStateMachine.complete(self.task, success=True)
            return result
        except GPUAllocationFailed:
            raise
        except TaskExecutionError as exc:
            TaskStateMachine.complete(self.task, success=False, error_message=exc.message)
            raise
        except Exception as exc:
            TaskStateMachine.complete(self.task, success=False, error_message=str(exc))
            raise TaskExecutionError(f"Unexpected error: {exc}") from exc
        finally:
            await self._release_gpu()
