"""任务执行器工厂与 GPU 生命周期编排。"""

import logging
import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from app.models.tasks import TaskStatus
from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.errors import (
    GPUAllocationFailed,
    RemoteCapacityLeaseLost,
    ResourceLeaseLost,
    ResourceAdmissionFailed,
    TaskExecutionError,
)
from app.tasks.attempts import get_execution_attempt_id
from app.tasks.executors.resolver import ExecutorResolver
from app.execution.service import ExecutionService
from app.tasks.resource_admission import ResourceAdmissionPolicy, WorkerCapability
from app.tasks.resource_lease import (
    WorkerResourceLeaseManager,
    mark_task_resource_reservation_claimed,
)
from app.tasks.resource_profile import (
    ResourceRequest,
    apply_resource_request_to_config,
    resource_request_from_snapshot,
)
from app.tasks.remote_capacity import (
    HEARTBEAT_INTERVAL_SECONDS as REMOTE_CAPACITY_HEARTBEAT_INTERVAL_SECONDS,
    RemoteCapacityLeaseDecision,
    RemoteCapacityLeaseManager,
    remote_capacity_policy,
)
from app.tasks.state_machine import DEFAULT_MAX_RETRIES, TaskStateMachine

if TYPE_CHECKING:
    from app.models.tasks import Task
    from app.models.tools import ToolVersion

logger = logging.getLogger(__name__)

def supported_executor_types() -> tuple[str, ...]:
    """返回 V1 Executor Gateway 已登记的执行器类型。"""
    return ExecutorResolver().supported_types()


class TaskExecutor:
    """按工具类型选择执行器并管理资源与 GPU 生命周期。"""

    def __init__(
        self,
        task: "Task",
        tool_version: "ToolVersion",
        tool: Optional[Any] = None,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
        executor_resolver: ExecutorResolver | None = None,
        cache_client=None,
        worker_capability: WorkerCapability | None = None,
        execution_service: ExecutionService | None = None,
        db_session: Any | None = None,
    ):
        self.task = task
        self.tool_version = tool_version
        self.progress_callback = progress_callback
        self.executor_resolver = executor_resolver or ExecutorResolver()
        self.cache_client = cache_client
        self.worker_capability = worker_capability
        self.execution_service = execution_service
        self.db_session = db_session
        self._allocation_id: str | None = None
        self._gpu_heartbeat_task: asyncio.Task[None] | None = None
        self._resource_lease_manager: WorkerResourceLeaseManager | None = None
        self._resource_lease_id: str | None = None
        self._resource_lease_ttl_seconds: int | None = None
        self._resource_lease_heartbeat_task: asyncio.Task[None] | None = None
        self._resource_lease_owner_task: asyncio.Task | None = None
        self._resource_lease_lost = False
        self._remote_capacity_manager: RemoteCapacityLeaseManager | None = None
        self._remote_capacity_lease: RemoteCapacityLeaseDecision | None = None
        self._remote_capacity_heartbeat_task: asyncio.Task[None] | None = None
        self._remote_capacity_owner_task: asyncio.Task | None = None
        self._remote_capacity_lost = False
        self.config = dict(tool_version.config or {})
        resource_snapshot = (
            task.extra_data.get("resource_snapshot")
            if isinstance(getattr(task, "extra_data", None), dict)
            else None
        )
        if isinstance(resource_snapshot, dict):
            apply_resource_request_to_config(self.config, resource_snapshot)
        if tool is not None:
            if not isinstance(resource_snapshot, dict):
                self.config["gpu_required"] = bool(tool.gpu_required)
                if tool.gpu_required:
                    self.config["gpu_memory_required_mb"] = int(tool.gpu_memory_mb or 4096)

    def _get_executor(self) -> BaseExecutor:
        executor_type = str(self.config.get("type") or "")
        executor_class = self.executor_resolver.resolve(executor_type)
        executor_kwargs = {
            "config": self.config,
            "progress_callback": self.progress_callback,
            "db_session": self.db_session,
        }
        if executor_type == "k8s_job":
            executor_kwargs["execution_service"] = self.execution_service
        return executor_class(
            self.task,
            self.tool_version,
            **executor_kwargs,
        )

    def _admit_resources(self) -> None:
        """在执行前校验任务请求是否落在声明的 Worker 能力内。"""
        if self.worker_capability is None:
            return

        request = self._build_resource_request()
        decision = ResourceAdmissionPolicy.evaluate(
            request,
            self.worker_capability,
        )
        if decision.admitted:
            return

        raise ResourceAdmissionFailed(
            f"资源准入失败: {decision.reason}",
            reason=decision.reason or "no_capable_worker",
            worker_id=decision.worker_id or None,
            details={
                "reason": decision.reason,
                "worker_id": decision.worker_id,
            },
        )

    def _build_resource_request(self) -> ResourceRequest:
        snapshot = (
            self.task.extra_data.get("resource_snapshot")
            if isinstance(getattr(self.task, "extra_data", None), dict)
            else None
        )
        return resource_request_from_snapshot(self.config, snapshot)

    def _get_cache_client(self):
        from app.cache import get_cache

        return self.cache_client if self.cache_client is not None else get_cache()

    def _build_resource_lease_id(self) -> str:
        attempt_id = get_execution_attempt_id(self.task)
        return f"{self.task.id}:{attempt_id or 'current'}"

    def _needs_dynamic_resource_lease(self) -> bool:
        capability = self.worker_capability
        if capability is None:
            return False
        if any(
            value is not None
            for value in (
                capability.cpu_capacity,
                capability.memory_capacity_gb,
                capability.parallelism,
            )
        ):
            return True

        extra_data = self.task.extra_data if isinstance(self.task.extra_data, dict) else {}
        dispatch = extra_data.get("dispatch")
        reservation = dispatch.get("resource_reservation") if isinstance(dispatch, dict) else None
        return isinstance(reservation, dict) and reservation.get("status") not in {
            "released",
            "release_failed",
            "not_found",
        }

    async def _acquire_resources(self) -> None:
        self._admit_resources()
        await self._acquire_remote_capacity()
        if not self._needs_dynamic_resource_lease():
            return

        try:
            extra_data = self.task.extra_data if isinstance(self.task.extra_data, dict) else {}
            dispatch = extra_data.get("dispatch")
            reservation = dispatch.get("resource_reservation") if isinstance(dispatch, dict) else None
            reserved_worker_id = (
                str(reservation.get("worker_id") or "").strip()
                if isinstance(reservation, dict)
                else ""
            )
            if reserved_worker_id and reserved_worker_id != self.worker_capability.worker_id:
                raise ResourceAdmissionFailed(
                    "任务被非目标 Worker 接收，等待重新路由",
                    reason="reservation_worker_mismatch",
                    worker_id=self.worker_capability.worker_id,
                    details={
                        "reserved_worker_id": reserved_worker_id,
                        "actual_worker_id": self.worker_capability.worker_id,
                    },
                )

            request = self._build_resource_request()
            manager = WorkerResourceLeaseManager(cache=self._get_cache_client())
            decision = await manager.acquire(
                capability=self.worker_capability,
                request=request,
                lease_id=self._build_resource_lease_id(),
                lease_phase="running",
                user_id=str(getattr(self.task, "user_id", "") or "") or None,
                project_id=str(getattr(self.task, "project_id", "") or "") or None,
            )
            if not decision.acquired:
                raise ResourceAdmissionFailed(
                    f"资源动态占用失败: {decision.reason}",
                    reason=decision.reason or "resource_capacity_exhausted",
                    worker_id=decision.worker_id or None,
                    details={
                        "reason": decision.reason,
                        "worker_id": decision.worker_id,
                    },
                )
            self._resource_lease_manager = manager
            self._resource_lease_id = decision.lease_id
            self._resource_lease_ttl_seconds = manager.lease_ttl_seconds(request, None)
            self._resource_lease_owner_task = asyncio.current_task()
            mark_task_resource_reservation_claimed(
                self.task,
                worker_id=decision.worker_id,
            )
            self._start_resource_lease_heartbeat()
        except Exception:
            await self._release_remote_capacity()
            raise

    async def _acquire_remote_capacity(self) -> None:
        if self.config.get("type") != "remote_api":
            return
        policy = remote_capacity_policy(self.config)
        if not policy.managed:
            return
        manager = RemoteCapacityLeaseManager(cache=self._get_cache_client())
        request = self._build_resource_request()
        decision = await manager.acquire(
            policy=policy,
            lease_id=self._build_resource_lease_id(),
            timeout_sec=request.timeout_sec,
        )
        if not decision.acquired:
            if decision.reason == "remote_capacity_limit_mismatch":
                raise TaskExecutionError(
                    "容量共享组并发上限与已有工具不一致；请统一上限后重试",
                    details={"capacity_group": decision.capacity_group},
                )
            raise ResourceAdmissionFailed(
                "远程 API 服务容量已满，任务等待重试",
                reason=decision.reason or "remote_capacity_exhausted",
                details={"capacity_group": decision.capacity_group},
            )
        self._remote_capacity_manager = manager
        self._remote_capacity_lease = decision
        self._remote_capacity_owner_task = asyncio.current_task()
        self._start_remote_capacity_heartbeat(policy, request.timeout_sec)

    def _start_remote_capacity_heartbeat(self, policy, timeout_sec: int) -> None:
        if self._remote_capacity_heartbeat_task is not None or self._remote_capacity_lease is None:
            return
        self._remote_capacity_heartbeat_task = asyncio.create_task(
            self._remote_capacity_heartbeat_loop(policy, timeout_sec)
        )

    async def _remote_capacity_heartbeat_loop(self, policy, timeout_sec: int) -> None:
        while True:
            await asyncio.sleep(REMOTE_CAPACITY_HEARTBEAT_INTERVAL_SECONDS)
            manager = self._remote_capacity_manager
            decision = self._remote_capacity_lease
            if manager is None or decision is None:
                return
            try:
                if not await manager.heartbeat(
                    decision=decision,
                    ttl_seconds=policy.lease_ttl_seconds or timeout_sec + 60,
                ):
                    self._remote_capacity_lost = True
                    owner_task = self._remote_capacity_owner_task
                    if owner_task is not None and owner_task is not asyncio.current_task():
                        owner_task.cancel()
                    return
            except Exception:
                logger.exception("Failed to heartbeat remote capacity lease for task %s", self.task.id)
                self._remote_capacity_lost = True
                owner_task = self._remote_capacity_owner_task
                if owner_task is not None and owner_task is not asyncio.current_task():
                    owner_task.cancel()
                return

    async def _release_remote_capacity(self) -> None:
        heartbeat_task = self._remote_capacity_heartbeat_task
        self._remote_capacity_heartbeat_task = None
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
        manager = self._remote_capacity_manager
        decision = self._remote_capacity_lease
        self._remote_capacity_manager = None
        self._remote_capacity_lease = None
        self._remote_capacity_owner_task = None
        if manager is not None and decision is not None:
            try:
                await manager.release(decision=decision)
            except Exception:
                logger.exception("Failed to release remote capacity lease for task %s", self.task.id)

    def _start_resource_lease_heartbeat(self) -> None:
        if (
            self._resource_lease_manager is None
            or self._resource_lease_id is None
            or self._resource_lease_heartbeat_task is not None
        ):
            return
        self._resource_lease_heartbeat_task = asyncio.create_task(
            self._resource_lease_heartbeat_loop()
        )

    async def _stop_resource_lease_heartbeat(self) -> None:
        heartbeat_task = self._resource_lease_heartbeat_task
        self._resource_lease_heartbeat_task = None
        if heartbeat_task is None:
            return
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task

    async def _resource_lease_heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(WorkerResourceLeaseManager.HEARTBEAT_INTERVAL_SECONDS)
            manager = self._resource_lease_manager
            lease_id = self._resource_lease_id
            capability = self.worker_capability
            ttl_seconds = self._resource_lease_ttl_seconds
            if (
                manager is None
                or lease_id is None
                or capability is None
                or ttl_seconds is None
            ):
                return
            try:
                refreshed = await manager.heartbeat(
                    worker_id=capability.worker_id,
                    lease_id=lease_id,
                    ttl_seconds=ttl_seconds,
                )
                if not refreshed:
                    logger.warning(
                        "Resource lease expired for task %s",
                        self.task.id,
                    )
                    self._resource_lease_lost = True
                    owner_task = self._resource_lease_owner_task
                    if owner_task is not None and owner_task is not asyncio.current_task():
                        owner_task.cancel()
                    return
            except Exception as exc:
                logger.warning(
                    "Failed to heartbeat resource lease for task %s: %s",
                    self.task.id,
                    exc,
                )
                # A failed heartbeat cannot prove that the lease still exists.
                # Stop this attempt before the TTL expires and another task
                # can be admitted for the same capacity.
                self._resource_lease_lost = True
                owner_task = self._resource_lease_owner_task
                if owner_task is not None and owner_task is not asyncio.current_task():
                    owner_task.cancel()
                return

    async def _release_resource_lease(self) -> None:
        await self._stop_resource_lease_heartbeat()
        manager = self._resource_lease_manager
        lease_id = self._resource_lease_id
        capability = self.worker_capability
        self._resource_lease_manager = None
        self._resource_lease_id = None
        self._resource_lease_ttl_seconds = None
        self._resource_lease_owner_task = None
        if manager is None or lease_id is None or capability is None:
            return
        try:
            await manager.release(
                worker_id=capability.worker_id,
                lease_id=lease_id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to release resource lease for task %s: %s",
                self.task.id,
                exc,
            )

    def _get_gpu_allocator(self, session):
        from app.gpu.allocator import GPUAllocator

        return GPUAllocator(session, cache_client=self._get_cache_client())

    async def _allocate_gpu(self) -> Optional[dict[str, Any]]:
        if not self.config.get("gpu_required", False):
            return None
        executor_type = str(self.config.get("type") or "").strip()
        if executor_type in {"k8s_job", "remote_api", "ssh_job"}:
            return None
        from app.database.session import get_async_session

        async for session in get_async_session():
            try:
                allocation_kwargs = {
                    "task_id": str(self.task.id),
                    "memory_required_mb": self.config.get("gpu_memory_required_mb", 4096),
                }
                attempt_id = get_execution_attempt_id(self.task)
                if attempt_id is not None:
                    allocation_kwargs["attempt_id"] = attempt_id
                result = await self._get_gpu_allocator(session).allocate(
                    **allocation_kwargs
                )
                if not result.success:
                    raise GPUAllocationFailed(
                        result.message or "No GPU resources available",
                        wait_position=result.wait_position,
                    )
                self._allocation_id = result.allocation_id
                self.task.gpu_node_id, self.task.gpu_index = result.gpu_node_id, result.gpu_index
                self.task.gpu_memory_allocated_mb = result.allocated_memory_mb
                gpu_config = dict(self.config.get("gpu_config") or {})
                gpu_config["count"] = 1
                gpu_config["device"] = str(result.gpu_index)
                self.config["gpu_config"] = gpu_config
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

        async for session in get_async_session():
            try:
                release_kwargs = {"task_id": str(self.task.id)}
                if self._allocation_id is not None:
                    release_kwargs["allocation_id"] = self._allocation_id
                await self._get_gpu_allocator(session).release(**release_kwargs)
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
        from app.gpu.allocator import GPU_LEASE_HEARTBEAT_INTERVAL_SECONDS

        while True:
            await asyncio.sleep(GPU_LEASE_HEARTBEAT_INTERVAL_SECONDS)
            if self._allocation_id is None:
                return

            from app.database.session import get_async_session

            async for session in get_async_session():
                try:
                    await self._get_gpu_allocator(session).heartbeat(
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
        try:
            await self._acquire_resources()
            executor = self._get_executor()
            await self._allocate_gpu()
            return await executor.execute()
        except asyncio.CancelledError:
            if self._remote_capacity_lost:
                raise RemoteCapacityLeaseLost()
            if self._resource_lease_lost:
                raise ResourceLeaseLost(
                    worker_id=(self.worker_capability.worker_id if self.worker_capability else None)
                )
            raise
        except (GPUAllocationFailed, TaskExecutionError):
            raise
        except Exception as exc:
            logger.exception("Task %s unexpected error", self.task.id)
            raise TaskExecutionError(f"Unexpected error: {exc}") from exc
        finally:
            try:
                await self._release_gpu()
            finally:
                try:
                    await self._release_resource_lease()
                finally:
                    await self._release_remote_capacity()

    async def execute_with_progress(
        self,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> dict[str, Any]:
        async def report(progress: float, message: str) -> None:
            TaskStateMachine.update_progress(self.task, progress, message)
            if progress_callback:
                await progress_callback(progress, message)

        try:
            await self._acquire_resources()
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
        except asyncio.CancelledError:
            if self._remote_capacity_lost:
                raise RemoteCapacityLeaseLost()
            if self._resource_lease_lost:
                raise ResourceLeaseLost(
                    worker_id=(self.worker_capability.worker_id if self.worker_capability else None)
                )
            raise
        except TaskExecutionError as exc:
            if self._is_running():
                TaskStateMachine.complete(self.task, success=False, error_message=exc.message)
            raise
        except Exception as exc:
            if self._is_running():
                TaskStateMachine.complete(self.task, success=False, error_message=str(exc))
            raise TaskExecutionError(f"Unexpected error: {exc}") from exc
        finally:
            try:
                await self._release_gpu()
            finally:
                try:
                    await self._release_resource_lease()
                finally:
                    await self._release_remote_capacity()

    def _is_running(self) -> bool:
        status = self.task.status
        if isinstance(status, TaskStatus):
            status = status.value
        return status == TaskStatus.RUNNING.value
