"""请求级幂等的 HTTP 层接入（``X-Idempotency-Key``，docs/05 §12）。

本模块只做「读请求头 → 问服务层 → 按判定结果短路或放行」这一件事，判定逻辑
全部在 ``app.services.idempotency``。这里提供的是一个**路由装饰器**：

.. code-block:: python

    @router.post("", response_model=dict)
    @idempotent_route(path_template="/api/v1/tasks", resource_type="task")
    async def create_task(task_data: TaskCreate, request: Request, ...):
        ...

为什么是装饰器，而不是 ``BaseHTTPMiddleware``
--------------------------------------------
``BaseHTTPMiddleware`` 里 ``call_next`` 返回的响应体是**流**，要在不破坏流式接口
（本仓 ``tasks.py`` 里有多个 ``StreamingResponse``）的前提下把首响快照读出来，只能
把整个响应体缓冲下来再回放——一旦响应很大或无限长就会挂住。装饰器拿到的是路由
函数的**返回值**（``dict`` 信封），直接就是可 JSON 化的对象，既能精确落快照，也不
会干扰流式端点。

依赖（``Depends``）方案同样被排除：``yield`` 依赖的收尾代码拿不到路由的返回值，
只能看到「有没有抛异常」，无法区分 200 / 4xx / 5xx，也就无法实现「2xx 才落快照、
其余释放键」这条核心语义。

代价是路由函数必须显式声明一个 ``request: Request`` 参数（FastAPI 会注入，不需要
额外依赖，也不会出现在 OpenAPI 里）。这是**唯一**的额外要求，并且只对启用了幂等
的那一个端点成立。

为什么不做全局中间件
--------------------
幂等键是**可选**的语义：没带头的请求必须原样放行。做成全局中间件意味着每个请求都
要过一遍路径匹配，且一旦匹配写错就会让现存 190+ 个端点集体改变行为。用装饰器时
「哪些端点有幂等义务」直接写在路由定义旁边，改一个端点不会波及其它端点。规格要求
的「不能把 X-Idempotency-Key 变成所有端点的强制要求」在这里是结构性保证，而不是
靠白名单列表维护。

失败必须把键还回去
------------------
``release_request`` 的三条触发路径都在这里：

* 路由抛异常（含 5xx）→ 先 ``rollback`` 再删行，然后**原样抛出**，错误响应仍由
  ``main.py`` 的 ``AppException`` / 兜底 handler 生成；
* 路由返回非 2xx → 同样删行，让客户端能用同一个键重试；
* 快照落不下去（返回值不是可 JSON 化的形态）→ 删行，退化回「没有幂等」，绝不返回
  一个伪造的重放。
"""

from __future__ import annotations

import functools
import json
import logging
from typing import Any, Callable, Optional

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ValidationException
from app.common.responses import error_response
from app.config import settings
from app.models.idempotency import IDEMPOTENCY_RETRY_AFTER_SECONDS
from app.services.idempotency import (
    OUTCOME_CONFLICT_BODY,
    OUTCOME_IN_FLIGHT,
    OUTCOME_REPLAY,
    begin_request,
    build_scope,
    complete_request,
    hash_request,
    release_request,
)

logger = logging.getLogger(__name__)

#: 与 ``idempotency_keys.key`` 的列宽一致；超长键无处可存，直接拒绝。
MAX_IDEMPOTENCY_KEY_LENGTH = 128

#: 幂等键请求头（大小写不敏感，Starlette 的 headers 本身就是小写索引）。
IDEMPOTENCY_HEADER = "X-Idempotency-Key"

#: 错误码（docs/05 §1.3）。``code`` 放在响应体里：``AppException`` 的 ``code``
#: 字段就是 HTTP 状态码，没有 409xx 通道。
CODE_IDEMPOTENCY_IN_FLIGHT = 40904
CODE_IDEMPOTENCY_KEY_REUSED = 40905


def _conflict_key_reused_response() -> JSONResponse:
    """同键异体 → 409 / 40905。"""
    return JSONResponse(
        status_code=409,
        content=error_response("幂等键复用但请求体不同", code=CODE_IDEMPOTENCY_KEY_REUSED),
    )


def _in_flight_response() -> JSONResponse:
    """同键且首次请求仍在处理中 → 409 / 40904 + ``Retry-After``。"""
    return JSONResponse(
        status_code=409,
        content=error_response(
            "同一幂等键的首次请求仍在处理中，请稍后重试",
            code=CODE_IDEMPOTENCY_IN_FLIGHT,
        ),
        headers={"Retry-After": str(IDEMPOTENCY_RETRY_AFTER_SECONDS)},
    )


def _split_result(result: Any) -> Optional[tuple[int, Any]]:
    """把路由返回值拆成 ``(status_code, json_body)``；拆不出来返回 ``None``。

    只接受两种形态：``success_response`` 之类的 ``dict`` 信封，以及 ``JSONResponse``。
    其它 ``Response``（文件下载、流式响应）没有被快照的意义，返回 ``None`` 让调用方
    释放幂等键。

    落库前必须过一遍 ``jsonable_encoder``：信封里带 ``datetime``（``created_at``
    之类），直接塞进 JSON 列会在序列化阶段炸掉。这一步同时把「不可 JSON 化」的
    返回值暴露成 ``None``，避免写进一个半成品快照。
    """
    if isinstance(result, dict):
        status_code, body = 200, result
    elif isinstance(result, JSONResponse):
        try:
            body = json.loads(result.body) if result.body else None
        except (TypeError, ValueError):
            return None
        status_code = result.status_code
    elif isinstance(result, Response):
        return None
    else:
        status_code, body = 200, result

    try:
        return status_code, jsonable_encoder(body)
    except (TypeError, ValueError):
        return None


def _resource_id_from_body(body: Any) -> Optional[str]:
    """从统一响应信封里取首响创建出来的资源 id（``data.id``），仅用于排查。"""
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if isinstance(data, dict):
        candidate = data.get("id")
        if isinstance(candidate, str):
            return candidate
    return None


async def _release_quietly(db: AsyncSession, *, scope: str, key: str) -> None:
    """尽力删掉幂等行，**不能让清理动作掩盖原始错误**。

    正常情况下（业务代码自己抛异常、事务仍然健康）直接删即可。只有会话已经停在
    「事务失效」状态（路由里某条 SQL 报错后未回滚，此时任何语句都会抛
    ``PendingRollbackError``）才先 ``rollback`` 再重试一次。

    为什么不一上来就 ``rollback``：``rollback`` 会让会话里所有对象过期，而本仓不少
    调用方在同一个会话里持有对象（测试尤为明显），随后访问属性会触发异步环境下的
    隐式懒加载（``MissingGreenlet``）——清理动作本应是隐形的，不能改变会话状态。

    连删都失败就记日志放弃：键最坏情况是占满 TTL，比丢失原始错误可接受得多。
    """
    try:
        await release_request(db, scope=scope, key=key)
        return
    except Exception:  # noqa: BLE001 - 事务失效时才有必要回滚重试
        logger.debug("释放幂等键遇到失效事务，回滚后重试 scope=%s key=%s", scope, key)
    try:
        await db.rollback()
        await release_request(db, scope=scope, key=key)
    except Exception:  # noqa: BLE001 - 清理失败不应影响错误传播
        logger.warning("释放幂等键失败 scope=%s key=%s", scope, key, exc_info=True)


def idempotent_route(
    *,
    path_template: str,
    resource_type: Optional[str] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """给单个路由启用请求级幂等（docs/05 §12）。

    ``path_template`` 必须是路由模板（``/api/v1/tasks``）而不是真实路径：scope 用
    模板，同一个接口的不同资源才会共享作用域，客户端在不同资源上误用同一个键时才
    能被 40905 拦住。

    没带 ``X-Idempotency-Key`` 或 ``IDEMPOTENCY_ENABLED=false`` 时完全透传，不产生
    任何数据库读写。
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request: Optional[Request] = kwargs.get("request")
            db: Optional[AsyncSession] = kwargs.get("db")
            current_user = kwargs.get("current_user")

            if not settings.IDEMPOTENCY_ENABLED or request is None or db is None:
                return await func(*args, **kwargs)

            raw_key = request.headers.get(IDEMPOTENCY_HEADER)
            # 空头等同于没带：客户端在「不想幂等」时偶尔会发空串。
            if raw_key is None or not raw_key.strip():
                return await func(*args, **kwargs)

            key = raw_key.strip()
            if len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
                raise ValidationException(
                    f"X-Idempotency-Key 长度不能超过 {MAX_IDEMPOTENCY_KEY_LENGTH} 个字符"
                )

            user_id = str(getattr(current_user, "id", "") or "")
            if not user_id:
                # 没有当前用户就没有稳定的作用域（不同人共用匿名作用域会互相串结果），
                # 这种端点在认证层就会被 401 拦掉，这里只是防御。
                return await func(*args, **kwargs)

            scope = build_scope(
                user_id=user_id, method=request.method, path_template=path_template
            )
            request_hash = hash_request(
                method=request.method,
                path=request.url.path,
                query=request.url.query,
                body=await request.body(),
            )

            outcome = await begin_request(
                db,
                scope=scope,
                key=key,
                request_hash=request_hash,
                user_id=user_id,
                ttl_hours=settings.IDEMPOTENCY_TTL_HOURS,
            )

            if outcome.status == OUTCOME_REPLAY and outcome.response is not None:
                status_code, body = outcome.response
                return JSONResponse(status_code=status_code, content=body)
            if outcome.status == OUTCOME_CONFLICT_BODY:
                return _conflict_key_reused_response()
            if outcome.status == OUTCOME_IN_FLIGHT:
                return _in_flight_response()

            # acquired：本次请求拿到执行权。
            try:
                result = await func(*args, **kwargs)
            except BaseException:
                await _release_quietly(db, scope=scope, key=key)
                raise

            snapshot = _split_result(result)
            if snapshot is None:
                await _release_quietly(db, scope=scope, key=key)
                return result

            status_code, body = snapshot
            if not 200 <= status_code < 300:
                await _release_quietly(db, scope=scope, key=key)
                return result

            await complete_request(
                db,
                scope=scope,
                key=key,
                status_code=status_code,
                body=body,
                resource_type=resource_type,
                resource_id=_resource_id_from_body(body),
            )
            return result

        return wrapper

    return decorator


__all__ = [
    "CODE_IDEMPOTENCY_IN_FLIGHT",
    "CODE_IDEMPOTENCY_KEY_REUSED",
    "IDEMPOTENCY_HEADER",
    "MAX_IDEMPOTENCY_KEY_LENGTH",
    "idempotent_route",
]
