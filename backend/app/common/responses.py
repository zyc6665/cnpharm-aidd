# backend/app/common/responses.py
"""统一响应格式（docs/05 §1.2）。

信封固定为 ``{code, message, data, requestId, timestamp}``：

* ``requestId`` 来自 ``app.common.trace`` 的 contextvar，即本次请求的 traceId
  （与响应头 ``X-Request-Id`` **同一个值**，方便前端把网络面板里的一行和日志对上）；
* ``timestamp`` 是服务端生成时间，带 ``Z`` 的 UTC ISO 字符串。

两者在「没有请求上下文」时（单测直接调 helper、脚本里拼信封）分别是 ``None``
与真实时间——**降级不抛错**：这些 helper 被 30+ 个模块调用，让它们依赖请求上下文
会把一次单测变成一个需要起 ASGI 栈的集成测试。
"""

from typing import Any, Optional

from app.common.time import isoformat_utc, utcnow
from app.common.trace import get_trace_id
from app.schemas.common import PaginatedResponse


def _envelope(code: int, message: str, data: Any) -> dict:
    """组装统一信封。

    ``requestId`` 显式取一次 contextvar 而不是在三个 helper 里各写一遍：
    将来换来源（比如从 ``request.scope`` 读）只改这里。
    """
    return {
        "code": code,
        "message": message,
        "data": data,
        "requestId": get_trace_id(),
        "timestamp": isoformat_utc(utcnow()),
    }


def success_response(
    data: Any = None,
    message: str = "success",
    code: int = 200
) -> dict:
    """成功响应"""
    return _envelope(code, message, data)


def paginated_response(
    *,
    items: list[Any],
    total: int,
    page: int,
    page_size: int,
    message: str = "success",
    code: int = 200,
) -> dict:
    """标准分页响应"""
    return success_response(
        data=PaginatedResponse.create(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump(),
        message=message,
        code=code,
    )


def error_response(
    message: str,
    code: int = 500,
    detail: Optional[Any] = None
) -> dict:
    """错误响应"""
    response = _envelope(code, message, None)
    if detail:
        response["detail"] = detail
    return response
