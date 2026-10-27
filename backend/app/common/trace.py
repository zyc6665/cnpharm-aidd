# backend/app/common/trace.py
"""请求链路 ID（traceId）的基础原语。

**为什么放在 ``app/common`` 而不是 ``app/middleware``**：需要读取 traceId 的地方
覆盖了 HTTP 之外的进程内路径（任务服务、审计、K8s 出站），而 ``app/middleware``
是 Starlette 的领域。把 contextvar 与解析函数放在 ``app/common``，可以让
``app/common/responses.py``、``app/logging/*``、``app/execution/transports/*``
在完全不 import Starlette 的前提下使用同一份状态；``app/middleware/trace.py``
只负责 ASGI 接线。

术语对齐 docs：

- docs/05 §1.1 用 ``X-Request-Id``，响应体里叫 ``requestId``，示例 ``req_01J...``；
- docs/10 §8.3 用 W3C ``traceparent`` 的 ``trace_id``；
- docs/10 §8.1 要求每条结构化日志都带 ``trace_id``（必填）。

本仓库把这三者统一成**一个**值：一个形如 ``req_01J...`` 的字符串既作为
``X-Request-Id`` 回写，也作为 ``requestId`` 返回，同时写进日志的 ``trace_id``
字段与 ``task.extra_data.traceId``（本仓库没有 ``env_json`` 列，见
``app/tasks/service.py`` 的注释）。不做两套 ID 是因为 docs/12 TC-NFR-09 要求
「按 traceId 串起全链路」——两套 ID 会让日志侧必须同时按两个键检索。
"""

from __future__ import annotations

import logging
import os
import re
import time
from contextvars import ContextVar, Token
from typing import Optional

__all__ = [
    "TRACE_ID_HEADER",
    "TRACEPARENT_HEADER",
    "PLACEHOLDER",
    "MAX_TRACE_ID_LENGTH",
    "new_trace_id",
    "get_trace_id",
    "set_trace_id",
    "reset_trace_id",
    "parse_traceparent",
    "normalize_incoming_trace_id",
    "TraceIdFilter",
    "trace_id_context",
]

#: 入站/出站请求头名（docs/05 §1.1）。
TRACE_ID_HEADER = "X-Request-Id"
#: W3C Trace Context 请求头（docs/10 §8.3）。
TRACEPARENT_HEADER = "traceparent"
#: 日志里 traceId 缺失时的占位符。docs/10 §8.1 把 ``trace_id`` 列为必填，
#: 所以宁可写 ``"-"`` 也不省略字段——省略会让日志检索侧的分组多出一个
#: 「字段不存在」的分支。
PLACEHOLDER = "-"
#: ``audit_logs.request_id`` 是 ``String(64)``，入站值必须在这里截断/拒绝，
#: 否则超长头会在写审计时被数据库截断成另一个 ID（跨表对不上）。
MAX_TRACE_ID_LENGTH = 64

#: 允许回显的入站 ID 字符集。不做白名单等于把客户端字符串直接写进日志与
#: 审计表：换行会撕裂日志行（日志注入），引号会破坏 JSON 结构。
_SAFE_TRACE_ID = re.compile(r"^[A-Za-z0-9._:\-]{1,%d}$" % MAX_TRACE_ID_LENGTH)

#: ``00-<32 hex trace-id>-<16 hex parent-id>-<flags>``（W3C trace-context）。
#: 只接受 version ``00``：version 更大时规范要求「按 00 解析并忽略尾部」，
#: 但上游目前只会发 00，收紧比放宽更容易发现对接错误。
_TRACEPARENT = re.compile(r"^00-(?P<trace_id>[0-9a-f]{32})-(?P<parent_id>[0-9a-f]{16})-([0-9a-f]{2})$")

#: 当前请求的 traceId。默认 ``None`` 表示「不在请求上下文里」（CLI、worker、
#: 单测直调），此时响应体 ``requestId`` 为 ``None`` 而不是抛错。
trace_id_context: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_crockford(value: int, length: int) -> str:
    """把整数编码成 Crockford Base32（ULID 用的字符表）。"""
    chars = []
    for _ in range(length):
        chars.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def new_trace_id() -> str:
    """生成新的 traceId，形如 ``req_01J9Z3K7Q0`` + 16 位随机段。

    采用 ULID 风格（48 位毫秒时间戳 + 80 位随机）而不是裸 ``uuid4().hex``：

    - docs/05 §1.2 的示例是 ``req_01J...``，前缀区分得很清楚，日志里一眼能看出
      这是本平台发的 ID 而不是上游 idempotency key；
    - 前缀是时间戳 → 按字典序排序即按时间排序，日志系统按 ID 排序时不会乱；
    - 时间戳 + 随机（而**不是**单调递增计数器）→ 多进程/多实例不需要协调。

    26 个字符 = 10 位时间 + 16 位随机，总长 30，远小于 ``String(64)``。
    """
    timestamp_ms = int(time.time() * 1000)
    randomness = int.from_bytes(os.urandom(10), "big")
    return f"req_{_encode_crockford(timestamp_ms, 10)}{_encode_crockford(randomness, 16)}"


def get_trace_id() -> Optional[str]:
    """返回当前上下文里的 traceId，没有则 ``None``。"""
    return trace_id_context.get()


def set_trace_id(value: Optional[str]) -> Token:
    """写入当前上下文的 traceId，返回可用于 ``reset_trace_id`` 的 token。"""
    return trace_id_context.set(value)


def reset_trace_id(token: Token) -> None:
    """按 token 复位 contextvar。

    必须用 token 而不是 ``set(None)``：并发请求共享同一个 contextvar 对象，
    token 复位能把外层（例如 ASGI 之外的调用方）恢复成它进入时的值。
    """
    trace_id_context.reset(token)


def parse_traceparent(header_value: Optional[str]) -> Optional[str]:
    """从 W3C ``traceparent`` 里取出 trace-id。

    非法格式**返回 None 而不是抛错**：这是客户端可控的请求头，上游代理发来
    截断值、日志中间件发来空串、或者恶意构造的垃圾都不能把请求打挂
    （docs/12 §4.9 只要求可追踪，没要求拒绝请求）。
    """
    if not header_value:
        return None
    match = _TRACEPARENT.match(header_value.strip())
    if match is None:
        return None
    trace_id = match.group("trace_id")
    # 全零 trace-id 在 W3C 规范里是「无效」的保留值。
    if trace_id == "0" * 32:
        return None
    return trace_id


def normalize_incoming_trace_id(header_value: Optional[str]) -> Optional[str]:
    """校验并规范化入站 ``X-Request-Id``。

    合法值原样返回（前缀 ``req_`` 或上游网关的任意形态都保留——docs/05 只承诺
    「服务端生成并回传」，跨系统联调时回显上游 ID 才能继续串链路）；超长或含
    危险字符时返回 ``None``，由调用方生成新 ID。
    """
    if not header_value:
        return None
    candidate = header_value.strip()
    if not candidate:
        return None
    if _SAFE_TRACE_ID.match(candidate) is None:
        return None
    return candidate


class TraceIdFilter(logging.Filter):
    """把 ``trace_id`` 注入每条 ``LogRecord``（docs/10 §8.1）。

    ``logging.Filter`` 而不是 ``Formatter``：字段在 record 上，JSON 格式化器与
    文本格式化器都能用同一份逻辑取到，换成 json 输出不需要再改一处。
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        if not getattr(record, "trace_id", None):
            record.trace_id = get_trace_id() or PLACEHOLDER
        return True
