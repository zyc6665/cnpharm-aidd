"""任务执行器工厂与 GPU 生命周期编排。"""

import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from app.models.tasks import TaskStatus
from app.models.tools import ToolType
from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.builtin import BuiltinExecutor
from app.tasks.executors.docker import DockerExecutor
from app.tasks.executors.errors import GPUAllocationFailed, TaskExecutionError
from app.tasks.executors.python_script import PythonScriptExecutor
from app.tasks.executors.remote_api import RemoteAPIExecutor
from app.tasks.state_machine import TaskStateMachine

if TYPE_CHECKING:
    from app.models.tasks import Task
    from app.models.tools import ToolVersion

logger = logging.getLogger(__name__)

SUPPORTED_EXECUTOR_TYPES = (
    "builtin",
    "python_script",
    "docker_image",
    "ssh_job",
    "remote_api",
)


def supported_executor_types() -> tuple[str, ...]:
    """返回 V1 Executor Gateway 已登记的执行器类型。"""
    return SUPPORTED_EXECUTOR_TYPES


class TaskExecutor:
    """按工具类型选择执行器并管理 GPU 生命周期。"""

    def __init__(
        self,
        task: "Task",
        tool_version: "ToolVersion",
        tool: Optional[Any] = None,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ):
        self.task = task
        self.tool_version = tool_version
        self.progress_callback = progress_callback
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
        from app.tasks.executors.ssh_job import SSHJobExecutor

        executors: dict[str, type[BaseExecutor]] = {
            ToolType.REMOTE_API.value: RemoteAPIExecutor,
            ToolType.DOCKER_IMAGE.value: DockerExecutor,
            ToolType.PYTHON_SCRIPT.value: PythonScriptExecutor,
            ToolType.SSH_JOB.value: SSHJobExecutor,
            "remote_api": RemoteAPIExecutor,
            "docker_image": DockerExecutor,
            "python_script": PythonScriptExecutor,
            "ssh_job": SSHJobExecutor,
            "builtin": BuiltinExecutor,
        }
        executor_type = self.config.get("type")
        if not executor_type:
            raise TaskExecutionError("Missing type in tool config")
        executor_class = executors.get(executor_type)
        if not executor_class:
            raise TaskExecutionError(f"Unsupported executor type: {executor_type}")
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
                result = await GPUAllocator(session).allocate(
                    task_id=str(self.task.id),
                    memory_required_mb=self.config.get("gpu_memory_required_mb", 4096),
                )
                if not result.success:
                    raise GPUAllocationFailed(
                        result.message or "No GPU resources available",
                        wait_position=result.wait_position,
                    )
                self.task.gpu_node_id, self.task.gpu_index = result.gpu_node_id, result.gpu_index
                self.task.gpu_memory_allocated_mb = result.allocated_memory_mb
                await session.commit()
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
        if not self.task.gpu_node_id:
            return
        from app.database.session import get_async_session
        from app.gpu.allocator import GPUAllocator

        async for session in get_async_session():
            try:
                await GPUAllocator(session).release(task_id=str(self.task.id))
                self.task.gpu_node_id = None
                self.task.gpu_index = None
                self.task.gpu_memory_allocated_mb = None
                await session.commit()
            except Exception as exc:
                logger.warning("Failed to release GPU allocation for task %s: %s", self.task.id, exc)

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
            await report(0, "任务准备中")
            TaskStateMachine.start(self.task)
            executor = self._get_executor()
            try:
                await self._allocate_gpu()
            except GPUAllocationFailed as exc:
                if self.task.retry_count < self.task.max_retries:
                    TaskStateMachine.transition(
                        self.task,
                        TaskStatus.PENDING,
                        progress_message=(
                            f"GPU分配失败: {exc.message}，"
                            f"重试 {self.task.retry_count}/{self.task.max_retries}"
                        ),
                    )
                else:
                    TaskStateMachine.complete(
                        self.task,
                        success=False,
                        error_message=(
                            f"GPU分配失败(已达最大重试 {self.task.max_retries}): "
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
