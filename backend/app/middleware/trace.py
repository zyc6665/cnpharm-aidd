# backend/app/middleware/trace.py
"""traceId 注入中间件（G-7）。

**用纯 ASGI 而不是 ``BaseHTTPMiddleware``**：

``BaseHTTPMiddleware`` 把 ``send`` 包成一个 anyio 内存对象流，再转发给下游
``send``。对 ``StreamingResponse``（以及 Starlette 的 SSE）来说，这意味着下游
每一次 ``send`` 都进队列、由外层任务再取出转发——首帧要等到外层任务被调度才
能出去，且下游异常/取消路径上外层可能已经不读了。本仓库有
``GET /api/v1/tasks/{task_id}/events`` 这条 SSE 长连接，缓冲首帧就等于「打开
任务详情页先白屏几秒」，是已知会被 ``BaseHTTPMiddleware`` 破坏的形态
（docs/12 TC-NFR-09 的「任务日志可检索」依赖它可用）。

纯 ASGI 只做三件事：把 response 的 header 追加一个、设置 contextvar、
在 ``finally`` 里复位——完全不介入 body 流，首帧照常立刻 flush。

对比：``RateLimitMiddleware`` 是 ``BaseHTTPMiddleware``；本中间件**不**跟它保持同样
形态，因为限流的 ``dispatch`` 只需读写请求/响应头（不转发 body 分片），而本中间件
位于它的**外层**——一旦也用 ``BaseHTTPMiddleware``，SSE 的每一帧都要多穿一层内存流。
纯 ASGI 这一层对 body 是零拷贝透传的。
"""

from __future__ import annotations

import logging

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.trace import (
    TRACE_ID_HEADER,
    TRACEPARENT_HEADER,
    new_trace_id,
    normalize_incoming_trace_id,
    parse_traceparent,
    reset_trace_id,
    set_trace_id,
)

logger = logging.getLogger(__name__)

#: 这些 scope 类型不参与追踪：``lifespan`` 没有请求头，``websocket`` 的响应
#: 头握手语义与 HTTP 不同（回写自定义头对浏览器无意义，且改了容易踩协议细节）。
_TRACED_SCOPES = frozenset({"http"})


def resolve_trace_id(scope: Scope) -> str:
    """按优先级决定本次请求的 traceId。

    1. 入站 ``X-Request-Id``（docs/05 §1.1 的名义主键；回显它才能让上游网关/
       前端日志继续串同一条链）——仅当它通过字符集与长度校验；
    2. 入站 ``traceparent`` 的 trace-id（docs/10 §8.3 的 W3C 透传）；
    3. 都没有（或都非法）才生成。

    注意第 1 步非法时**继续尝试第 2 步**而不是直接生成：网关常同时发两个头，
    一个被截断不该让合法的 traceparent 一起失效。
    """
    headers = Headers(scope=scope)
    incoming = normalize_incoming_trace_id(headers.get(TRACE_ID_HEADER))
    if incoming is not None:
        return incoming
    from_traceparent = parse_traceparent(headers.get(TRACEPARENT_HEADER))
    if from_traceparent is not None:
        return from_traceparent
    return new_trace_id()


class TraceIdMiddleware:
    """读取/生成 traceId，写入 contextvar 与响应头，请求结束复位。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in _TRACED_SCOPES:
            await self.app(scope, receive, send)
            return

        trace_id = resolve_trace_id(scope)
        # 塞回 scope：下游（如审计、K8s 出站）通过 request.scope 也能拿到，
        # 不必只依赖 contextvar 的隐式传递。
        scope.setdefault("state", {})["trace_id"] = trace_id

        async def send_with_trace_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                # 覆盖而不是 append：上游若已经自己写过同名头（例如异常处理器
                # 里手写），重复的 X-Request-Id 会让客户端取到哪一个变得随机。
                headers[TRACE_ID_HEADER] = trace_id
            await send(message)

        token = set_trace_id(trace_id)
        try:
            await self.app(scope, receive, send_with_trace_id)
        finally:
            # 必须复位：ASGI 中间件实例在应用生命周期内是单例，contextvar 又不
            # 随请求自动清理，漏掉这一步会让「上一个请求的 traceId」泄漏到
            # 下一个请求（并发下表现为两个请求互相串 ID）。
            reset_trace_id(token)
