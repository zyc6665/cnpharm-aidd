"""任务执行器共享异常类型。"""

from typing import Any


class TaskExecutionError(Exception):
    """任务执行错误。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class ResourceAdmissionFailed(TaskExecutionError):
    """Worker 当前无法承载任务资源请求，可触发延迟重入队。"""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        worker_id: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.reason = reason
        self.worker_id = worker_id
        merged_details = dict(details or {})
        merged_details.setdefault("reason", reason)
        merged_details.setdefault("worker_id", worker_id)
        super().__init__(message, details=merged_details)


class ResourceLeaseLost(ResourceAdmissionFailed):
    """运行中 lease 丢失，执行必须停止以避免资源超卖。"""

    def __init__(self, *, worker_id: str | None = None):
        super().__init__(
            "运行中的资源租约已丢失，任务必须停止",
            reason="resource_lease_lost",
            worker_id=worker_id,
        )


class RemoteCapacityLeaseLost(ResourceAdmissionFailed):
    """远程 API 容量租约丢失，执行必须停止以避免远程服务超卖。"""

    def __init__(self):
        super().__init__(
            "远程 API 容量租约已丢失，任务必须停止",
            reason="remote_capacity_lease_lost",
        )


class GPUAllocationFailed(TaskExecutionError):
    """GPU 资源分配失败，可触发重试逻辑。"""

    def __init__(
        self,
        message: str,
        wait_position: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.wait_position = wait_position
        merged_details = details or {}
        merged_details.setdefault("wait_position", wait_position)
        super().__init__(message, details=merged_details)
