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


class TooManyRequestsException(AppException):
    """请求过于频繁异常"""

    def __init__(self, message: str = "请求过于频繁", detail: Optional[Any] = None):
        super().__init__(message, code=429, detail=detail)


class BusinessException(AppException):
    """业务规则异常：``http_status`` 与信封业务码 ``code`` 可以不同。

    docs/05 把业务码（如 40002 参数非法、40101 未登录）与 HTTP 状态码分开；
    本异常让路由既能返回合适的 HTTP 状态（400/401/403），又能在响应体里给出
    稳定的业务码，供前端/测试按码分支。
    """

    def __init__(
        self,
        message: str,
        http_status: int = 400,
        code: int = 40002,
        detail: Optional[Any] = None,
    ):
        super().__init__(message, code=code, detail=detail)
        self.http_status = http_status
