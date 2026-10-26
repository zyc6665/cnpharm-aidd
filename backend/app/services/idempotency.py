"""请求级幂等（docs/04 §5.5、docs/05 §12、docs/18 §6.3 G-10）。

本模块只放**纯服务逻辑**：怎么拼 scope、怎么算请求哈希、怎么用一次原子写入抢占
幂等键。HTTP 相关的部分（读请求头、返回 40904/40905 信封）在
``app.middleware.idempotency``，两者分开是为了让服务层可以被后台任务与测试直接
调用，不需要构造 ``Request``。

三条语义（docs/05 §12）
-----------------------
* **同键同体**：``state == COMPLETED`` 且 ``request_hash`` 相同 → 返回首次响应
  快照，**不再执行**。
* **同键异体**：``request_hash`` 不同 → 40905，提示「幂等键复用但请求体不同」。
  绝不允许「以第一次为准」把 A 的响应交给 B。
* **同键且首次仍在处理中**：``state == IN_PROGRESS`` → 40904 + ``Retry-After``，
  让客户端稍后重试而不是并发执行第二次。

为什么用 ``INSERT ... ON CONFLICT DO NOTHING`` 抢锁
--------------------------------------------------
并发重试是两笔独立事务，「先查后插」之间必然存在窗口：两个事务都查到「不存在」，
然后各插一行，幂等就失效了。让数据库的唯一约束做仲裁，插入成功的那个事务拿到执行
权（``rowcount == 1``），插入被吞掉的那个去读既有行——这是在 SQLite 与 PostgreSQL
上行为一致、且不需要行锁的最小实现（SQLite 没有 ``SELECT ... FOR UPDATE``，一旦
依赖行锁，测试环境与生产就会得到不同行为）。

过期视为不存在
--------------
``expires_at <= now`` 的行不再拦请求：客户端隔了一天用同一个键发新请求是合法
重试，把它判成 409 只会让客户端永久卡死。这里直接覆盖成新请求（同一条 SQL 里
带上条件），而不是先删后插——先删后插在并发下会退化成两个事务都拿到执行权。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.config import settings
from app.models.idempotency import IdempotencyKey

#: 幂等键的生命周期状态（与模型常量同义，这里再导出一次方便服务层使用）。
STATE_IN_PROGRESS = "IN_PROGRESS"
STATE_COMPLETED = "COMPLETED"

#: ``IdempotencyOutcome.status`` 的取值。
OUTCOME_ACQUIRED = "acquired"
OUTCOME_REPLAY = "replay"
OUTCOME_CONFLICT_BODY = "conflict_body"
OUTCOME_IN_FLIGHT = "in_flight"

#: 单轮清理最多删多少行；防止某次积压把一轮跑成几分钟。
DEFAULT_PURGE_BATCH_SIZE = 200


def build_scope(*, user_id: str, method: str, path_template: str) -> str:
    """拼出幂等作用域 ``{user_id}:{METHOD}:{path_template}``（docs/05 §12）。

    ``path_template`` 必须是**路由模板**（``/api/v1/tasks/{task_id}``）而不是真实
    路径，否则同一个接口的不同资源会得到不同作用域，同一个键在不同资源上重复使用
    时无法被发现。
    """
    return f"{user_id}:{str(method).upper()}:{path_template}"


def hash_request(*, method: str, path: str, query: str, body: bytes) -> str:
    """算请求体指纹（sha256 十六进制）。

    四段都要进哈希：**同键不同 query 也是异体**。只哈希 body 会把
    ``POST /x?a=1`` 与 ``POST /x?a=2`` 判成同一个请求，客户端拿到的是另一次调用的
    结果。段之间插入长度前缀，避免 ``("ab", "c")`` 与 ``("a", "bc")`` 撞哈希。
    """
    digest = hashlib.sha256()
    for chunk in (
        str(method).upper().encode("utf-8"),
        str(path).encode("utf-8"),
        str(query or "").encode("utf-8"),
        body if body else b"",
    ):
        digest.update(len(chunk).to_bytes(8, "big"))
        digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class IdempotencyOutcome:
    """一次 ``begin_request`` 的判定结果。

    * ``acquired``：本次拿到执行权，调用方应继续执行业务逻辑。
    * ``replay``：命中首响快照，``response`` 是 ``(status_code, body)``，直接原样返回。
    * ``conflict_body``：同键异体，应返回 40905。
    * ``in_flight``：同键且首次仍在处理中，应返回 40904 + ``Retry-After``。
    """

    status: str
    record: Optional[IdempotencyKey] = None
    response: Optional[tuple[int, Any]] = None


def _dialect_name(db: AsyncSession) -> str:
    """从会话的 bind 取方言名，**不要用全局 engine**（测试会覆盖 bind）。"""
    bind = db.get_bind()
    return getattr(getattr(bind, "dialect", None), "name", "sqlite")


def _insert_statement(db: AsyncSession, values: dict):
    """按方言选 ``insert``；未知方言返回 ``None`` 由调用方退化成普通插入。"""
    dialect = _dialect_name(db)
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as _insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as _insert
    else:
        return None
    return _insert(IdempotencyKey).values(**values).on_conflict_do_nothing(
        index_elements=["scope", "key"]
    )


async def _load_record(db: AsyncSession, *, scope: str, key: str) -> Optional[IdempotencyKey]:
    """按主键读一行，``populate_existing`` 强制从库里刷新属性。

    没有这个选项时，若该行已在 session 的 identity map 里（同一请求内第二次
    ``begin_request``、或测试里共用一个会话），``select`` 会直接返回那个对象而**不
    刷新已被过期的属性**；async 环境下访问过期属性会抛 ``MissingGreenlet``。
    """
    result = await db.execute(
        select(IdempotencyKey)
        .where(IdempotencyKey.scope == scope, IdempotencyKey.key == key)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _try_insert(db: AsyncSession, values: dict) -> bool:
    """尝试插入一行 ``IN_PROGRESS``，返回是否真的插进去了。"""
    statement = _insert_statement(db, values)
    if statement is None:
        # 未知方言（理论上不会出现）：退化成普通 insert，冲突交给 IntegrityError。
        db.add(IdempotencyKey(**values))
        try:
            await db.flush()
        except Exception:  # noqa: BLE001 - 冲突即视为没抢到
            await db.rollback()
            return False
        return True
    result = await db.execute(statement)
    return (result.rowcount or 0) == 1


async def begin_request(
    db: AsyncSession,
    *,
    scope: str,
    key: str,
    request_hash: str,
    user_id: Optional[str] = None,
    ttl_hours: Optional[int] = None,
) -> IdempotencyOutcome:
    """抢占幂等键并给出本次请求该怎么处理（见模块 docstring 的三条语义）。

    插入成功即 ``acquired``；插入被吞掉说明键已存在，读出既有行再判：异体 →
    ``conflict_body``，已完成 → ``replay``，处理中 → ``in_flight``。既有行已过期
    时覆盖成新请求并返回 ``acquired``。

    调用方拿到 ``acquired`` 后必须在同一请求内调用 ``complete_request`` 或
    ``release_request``，否则这个键会被占满整个 TTL。
    """
    hours = settings.IDEMPOTENCY_TTL_HOURS if ttl_hours is None else ttl_hours
    now = utcnow()
    expires_at = now + _ttl_delta(hours)
    values = {
        "scope": scope,
        "key": key,
        "request_hash": request_hash,
        "state": STATE_IN_PROGRESS,
        "response_status": None,
        "response_body": None,
        "user_id": user_id,
        "resource_type": None,
        "resource_id": None,
        "created_at": now,
        "updated_at": now,
        "expires_at": expires_at,
    }

    if await _try_insert(db, values):
        await db.commit()
        return IdempotencyOutcome(
            status=OUTCOME_ACQUIRED, record=await _load_record(db, scope=scope, key=key)
        )

    # 注意：这里**不能** rollback。``on_conflict_do_nothing`` 是一条正常执行完的
    # INSERT（影响 0 行），事务是健康的；而 ``rollback`` 会把会话里所有对象标记为
    # 过期，调用方（路由）随后访问自己已经加载好的对象时就会触发异步环境下的隐式
    # 懒加载（MissingGreenlet）。只要不动事务，读既有行是安全的。
    existing = await _load_record(db, scope=scope, key=key)
    if existing is None:
        # 极端情况下既有行刚被 ``release_request`` 删掉（首次请求失败重试的竞态）。
        # 再抢一次；仍抢不到就当作处理中，让客户端稍后重试，绝不并发执行两次。
        if await _try_insert(db, values):
            await db.commit()
            return IdempotencyOutcome(
                status=OUTCOME_ACQUIRED, record=await _load_record(db, scope=scope, key=key)
            )
        return IdempotencyOutcome(status=OUTCOME_IN_FLIGHT)

    if existing.expires_at is not None and existing.expires_at <= now:
        existing.request_hash = request_hash
        existing.state = STATE_IN_PROGRESS
        existing.response_status = None
        existing.response_body = None
        existing.user_id = user_id
        existing.resource_type = None
        existing.resource_id = None
        existing.created_at = now
        existing.updated_at = now
        existing.expires_at = expires_at
        await db.commit()
        return IdempotencyOutcome(status=OUTCOME_ACQUIRED, record=existing)

    if existing.request_hash != request_hash:
        return IdempotencyOutcome(status=OUTCOME_CONFLICT_BODY, record=existing)

    if existing.state == STATE_COMPLETED:
        return IdempotencyOutcome(
            status=OUTCOME_REPLAY,
            record=existing,
            response=(existing.response_status or 200, existing.response_body),
        )

    return IdempotencyOutcome(status=OUTCOME_IN_FLIGHT, record=existing)


async def complete_request(
    db: AsyncSession,
    *,
    scope: str,
    key: str,
    status_code: int,
    body: Any,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
) -> None:
    """把行置 ``COMPLETED`` 并落首响快照。``body`` 必须是可 JSON 序列化的形态。"""
    record = await _load_record(db, scope=scope, key=key)
    if record is None:
        return
    record.state = STATE_COMPLETED
    record.response_status = int(status_code)
    record.response_body = body
    record.resource_type = resource_type
    record.resource_id = resource_id
    record.updated_at = utcnow()
    await db.commit()


async def release_request(db: AsyncSession, *, scope: str, key: str) -> None:
    """首次请求失败时整行删除，让客户端能用同一个键重试。

    **这条不能省**：如果失败也把键留在表里（无论是 ``IN_PROGRESS`` 还是写个失败
    快照），客户端拿着同一个键重试就永远只能拿到 40904/旧的错误响应，一次偶发的
    500 会把那个键永久「烧掉」，用户只能换一个键——而重试用的键是客户端在超时前
    就生成好的，换不了。因此失败路径必须把行删干净，把键还给客户端。

    与 ``complete_request`` 一样只删本行，不做级联：幂等表没有外键。
    """
    await db.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.scope == scope, IdempotencyKey.key == key
        )
    )
    await db.commit()


async def purge_expired_idempotency_keys(
    db: AsyncSession, *, batch_size: int = DEFAULT_PURGE_BATCH_SIZE, now=None
) -> int:
    """删除已过期的幂等行，返回删除条数（供后台清理循环调用）。

    只删 ``expires_at <= now`` 的行：未过期的行是「重放快照」，提前删掉会让同一个键
    的下一次重试变成全新请求，违反 24h 保留承诺。
    """
    moment = now or utcnow()
    result = await db.execute(
        select(IdempotencyKey.scope, IdempotencyKey.key)
        .where(IdempotencyKey.expires_at <= moment)
        .order_by(IdempotencyKey.expires_at.asc())
        .limit(max(int(batch_size), 0))
    )
    targets = [(row[0], row[1]) for row in result.all()]
    if not targets:
        return 0
    await db.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.expires_at <= moment,
            IdempotencyKey.scope.in_([scope for scope, _ in targets]),
        )
    )
    await db.commit()
    return len(targets)


def _ttl_delta(ttl_hours: int):
    from datetime import timedelta

    return timedelta(hours=max(int(ttl_hours), 1))


__all__ = [
    "DEFAULT_PURGE_BATCH_SIZE",
    "IdempotencyOutcome",
    "OUTCOME_ACQUIRED",
    "OUTCOME_CONFLICT_BODY",
    "OUTCOME_IN_FLIGHT",
    "OUTCOME_REPLAY",
    "STATE_COMPLETED",
    "STATE_IN_PROGRESS",
    "begin_request",
    "build_scope",
    "complete_request",
    "hash_request",
    "purge_expired_idempotency_keys",
    "release_request",
]
