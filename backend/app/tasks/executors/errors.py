"""任务执行器共享异常类型。"""

from typing import Any


class TaskExecutionError(Exception):
    """任务执行错误。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


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
