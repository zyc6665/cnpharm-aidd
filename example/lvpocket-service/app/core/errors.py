"""
统一错误处理模块

定义错误码、异常类和 FastAPI 异常处理器
"""

from enum import IntEnum
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse


class ErrorCode(IntEnum):
    """错误码枚举 - 与 API 文档保持一致"""

    # 客户端错误 (1xxx)
    INVALID_INPUT_FORMAT = 1001
    FILE_SIZE_EXCEEDED = 1002
    MISSING_REQUIRED_PARAM = 1003
    INVALID_PARAM_VALUE = 1004
    UNSUPPORTED_OUTPUT_FORMAT = 1005
    FILE_PARSE_FAILED = 1006
    INPUT_FILE_NOT_FOUND = 1007

    # 服务端错误 (2xxx)
    MODEL_LOAD_FAILED = 2001
    PREDICTION_FAILED = 2002
    CONVERSION_FAILED = 2003
    FILE_STORAGE_FAILED = 2004

    # 服务不可用 (3xxx)
    SERVICE_UNAVAILABLE = 3001
    GPU_RESOURCE_INSUFFICIENT = 3002
    REQUEST_TIMEOUT = 3003


# 错误码到 HTTP 状态码的映射
ERROR_CODE_TO_HTTP_STATUS: Dict[int, int] = {
    # 客户端错误 -> 400
    ErrorCode.INVALID_INPUT_FORMAT: 400,
    ErrorCode.FILE_SIZE_EXCEEDED: 400,
    ErrorCode.MISSING_REQUIRED_PARAM: 400,
    ErrorCode.INVALID_PARAM_VALUE: 400,
    ErrorCode.UNSUPPORTED_OUTPUT_FORMAT: 400,
    ErrorCode.FILE_PARSE_FAILED: 400,
    ErrorCode.INPUT_FILE_NOT_FOUND: 404,
    # 服务端错误 -> 500
    ErrorCode.MODEL_LOAD_FAILED: 500,
    ErrorCode.PREDICTION_FAILED: 500,
    ErrorCode.CONVERSION_FAILED: 500,
    ErrorCode.FILE_STORAGE_FAILED: 500,
    # 服务不可用 -> 503/504
    ErrorCode.SERVICE_UNAVAILABLE: 503,
    ErrorCode.GPU_RESOURCE_INSUFFICIENT: 503,
    ErrorCode.REQUEST_TIMEOUT: 504,
}


class LVPocketError(Exception):
    """LVPocket 服务基础异常类"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    @property
    def http_status(self) -> int:
        """获取对应的 HTTP 状态码"""
        return ERROR_CODE_TO_HTTP_STATUS.get(self.code, 500)

    def to_dict(self) -> Dict[str, Any]:
        """转换为响应字典"""
        return {
            "success": False,
            "error": {
                "code": int(self.code),
                "message": self.message,
                "details": self.details,
            },
        }


class ValidationError(LVPocketError):
    """验证错误"""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INVALID_PARAM_VALUE,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(code=code, message=message, details=details)


class FileError(LVPocketError):
    """文件处理错误"""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.FILE_PARSE_FAILED,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(code=code, message=message, details=details)


class PredictionError(LVPocketError):
    """预测错误"""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.PREDICTION_FAILED,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(code=code, message=message, details=details)


class ConversionError(LVPocketError):
    """格式转换错误"""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.CONVERSION_FAILED,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(code=code, message=message, details=details)


class ServiceUnavailableError(LVPocketError):
    """服务不可用错误"""

    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        code: ErrorCode = ErrorCode.SERVICE_UNAVAILABLE,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(code=code, message=message, details=details)


async def lvpocket_exception_handler(
    request: Request, exc: LVPocketError
) -> JSONResponse:
    """LVPocket 异常处理器"""
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_dict(),
    )


async def generic_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """通用异常处理器"""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": ErrorCode.PREDICTION_FAILED,
                "message": "Internal server error",
                "details": {"error_type": type(exc).__name__},
            },
        },
    )
