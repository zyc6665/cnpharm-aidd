"""统一错误定义。"""

from __future__ import annotations


class ToolServiceError(Exception):
    """业务级服务异常。"""

    def __init__(self, message: str, code: str = "TOOL_SERVICE_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)
