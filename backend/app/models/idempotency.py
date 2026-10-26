"""请求级幂等键（docs/04 §5.5、docs/05 §12、docs/18 §6.3 G-10）。

``X-Idempotency-Key`` 是「客户端重试不产生副作用」的唯一手段：网络超时后客户端
无法判断请求是否已经生效，只能带同一个键重发。此前的 ``ExecutionRecord.
idempotency_key``（``{task}:{id}:attempt:{key}``）只是内部执行标识、``upload_
sessions.idempotency_key`` 只管上传会话，两者都不能承担通用的「请求级重放」——
G-10 要求的是任何写接口都能复用的机制。

三个设计点必须解释清楚，否则后来人很容易「优化」成错误形态：

* **为什么用复合主键 ``(scope, key)`` 而不是 UUID 主键 + 唯一索引**
  唯一性必须由数据库承担：并发重试是两笔不同事务，应用层「先查后插」之间必然
  有窗口，两个事务都会查到「不存在」然后各插一行，幂等就失效了。复合主键让
  ``INSERT ... ON CONFLICT (scope, key) DO NOTHING`` 变成一次原子判定——插入成功
  的那一方拿到执行权，插入被吞掉的那一方必须去读既有行。用 UUID 主键 + 唯一索引
  同样可行，但要多一个用不上的代理键，且 ORM 的 ``session.get()`` 只能按单列查，
  反而更容易写出「先查后插」。复合主键也正是 SQLite 与 PostgreSQL 行为一致的
  最小共同点（docs/04 §5.8 的 ``upload_parts`` 出于同样理由用了复合主键）。

* **为什么存 ``request_hash``**
  幂等键是客户端生成的，客户端有 bug 时会拿同一个键发不同的请求体。如果直接复用
  别人的结果，B 请求会拿到 A 请求的响应（比如把别人的 ``taskId`` 返回给 B），
  这是数据越权而不只是「结果不对」。因此必须自己算请求体哈希并逐字节比对，
  不一致就拒绝（40905）而不是「以第一次为准」。

* **为什么存 ``response_body``**
  「同键同体」的语义是**返回首次的响应快照，不再执行**。若只存 ``resource_id``
  再重新查一遍库，第二次拿到的就是「当前状态」而不是「当时的响应」：任务可能已经
  跑完、进度已经是 100%，客户端会认为自己的创建请求返回了错乱的结果。快照必须是
  首响原样，包括 ``taskId``。

生命周期与「只追加」表不同：行会在 ``IN_PROGRESS`` → ``COMPLETED`` 之间迁移，
失败时会整行删除（让同一个键可以重试），过期后由清理任务删除。因此这里**不挂**
``traceability.py`` 的 ``_reject_mutation`` 守卫——那条守卫属于审计日志，本表的
状态机就是它存在的意义。所有写路径都收敛在 ``app.services.idempotency`` 里。

索引只在 ``__table_args__`` 声明（与 ``models/decisions.py`` 同一约定）：列上再写
``index=True`` 会让 ``Base.metadata.create_all``（开发/测试）与 Alembic（生产）
产生同名索引的两种来源，漂移只在生产暴露。
"""

from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String

from app.database.base import Base, TimestampMixin

#: 幂等记录的状态机：``IN_PROGRESS`` 表示首次请求还在处理中（此时同键同体再来一次
#: 必须返回 40904 让客户端稍后重试），``COMPLETED`` 表示已经把首响快照落库。
IDEMPOTENCY_STATES = ("IN_PROGRESS", "COMPLETED")

#: 首次请求处理中时给客户端的建议重试间隔（秒），对应 ``Retry-After`` 响应头。
IDEMPOTENCY_RETRY_AFTER_SECONDS = 2


class IdempotencyKey(Base, TimestampMixin):
    """请求级幂等记录（docs/04 §5.5）。"""

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        # 过期清理任务唯一的扫描条件；没有它每轮清理都是全表扫。
        Index("ix_idempotency_keys_expires_at", "expires_at"),
        # 排查用：「这个用户最近用哪些幂等键发过请求」。
        Index("ix_idempotency_keys_user_id", "user_id"),
    )

    #: ``{user_id}:{METHOD}:{path_template}``，例如 ``u_123:POST:/api/v1/tasks``。
    #: 放进主键而不是单独建列：不同用户、不同接口的同名键天然互不干扰，
    #: 客户端不需要自己拼前缀，也不会因为键碰撞互相拿到对方的响应。
    scope = Column(String(255), primary_key=True)
    #: 客户端请求头 ``X-Idempotency-Key`` 的原值。
    key = Column(String(128), primary_key=True)
    #: 请求体（含 method/path/query）的 sha256 十六进制串，用于「同键异体」判定。
    request_hash = Column(String(64), nullable=False)
    state = Column(String(16), nullable=False, default="IN_PROGRESS")
    #: 首响的 HTTP 状态码；``IN_PROGRESS`` 期间为 NULL。
    response_status = Column(Integer, nullable=True)
    #: 首响的完整响应体（统一响应信封），重放时原样返回。
    response_body = Column(JSON, nullable=True)
    user_id = Column(String(36), nullable=True)
    #: 首次请求创建出来的资源，便于线上排查「这个键对应哪个任务」。
    resource_type = Column(String(64), nullable=True)
    resource_id = Column(String(64), nullable=True)
    #: 保留期（默认 24h）。过期视为「键不存在」，客户端可以复用它发新请求。
    expires_at = Column(DateTime, nullable=False)


__all__ = [
    "IDEMPOTENCY_RETRY_AFTER_SECONDS",
    "IDEMPOTENCY_STATES",
    "IdempotencyKey",
]
