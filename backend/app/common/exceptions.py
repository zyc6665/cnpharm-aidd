# backend/app/common/exceptions.py
"""自定义异常类"""

from typing import Optional, Any


class AppException(Exception):
    """应用异常基类"""

    def __init__(
        self,
        message: str,
        code: int = 500,
        detail: Optional[Any] = None
    ):
        self.message = message
        self.code = code
        self.detail = detail
        super().__init__(message)


class NotFoundException(AppException):
    """资源不存在异常"""

    def __init__(self, message: str = "资源不存在", detail: Optional[Any] = None):
        super().__init__(message, code=404, detail=detail)


class ValidationException(AppException):
    """验证异常"""

    def __init__(self, message: str = "参数验证失败", detail: Optional[Any] = None):
        super().__init__(message, code=422, detail=detail)


class UnauthorizedException(AppException):
    """未授权异常"""

    def __init__(self, message: str = "未授权", detail: Optional[Any] = None):
        super().__init__(message, code=401, detail=detail)


class ForbiddenException(AppException):
    """禁止访问异常"""

    def __init__(self, message: str = "禁止访问", detail: Optional[Any] = None):
        super().__init__(message, code=403, detail=detail)


class ConflictException(AppException):
    """冲突异常"""

    def __init__(self, message: str = "资源冲突", detail: Optional[Any] = None):
        super().__init__(message, code=409, detail=detail)


class QuotaExceededException(AppException):
    """配额超出异常"""

    def __init__(self, message: str = "配额超出", detail: Optional[Any] = None):
        super().__init__(message, code=429, detail=detail)
