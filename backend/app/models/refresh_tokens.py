# backend/app/models/refresh_tokens.py
"""Refresh Token 持久化模型（jti 存储 / 轮换 / 复用检测）。

设计要点（docs/22 P2 认证授权）：
* refresh token 仍是无状态 JWT，但签发的每个 ``jti`` 都会落库一行；
* 轮换时旧 jti 标记 ``revoked_at`` 并写 ``replaced_by``，新 jti 另起一行；
* 已吊销的 jti 再次出现即视为「复用入侵」，吊销该用户全部 refresh；
* access token 不落库，保持短寿命。

时间列沿用全仓约定：naive UTC（见 ``app.common.time.utcnow``）。
"""

from sqlalchemy import Column, DateTime, ForeignKey, String

from app.common.time import utcnow
from app.database.base import Base


class RefreshToken(Base):
    """refresh token 的 jti 白名单/吊销账本。"""

    __tablename__ = "refresh_tokens"

    #: JWT 里的 jti 声明，作为主键（不额外引入自增/UUID 主键）。
    jti = Column(String(36), primary_key=True)
    #: 归属用户；用户删除时级联清理其 refresh 记录。
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: 过期时间（naive UTC），与 JWT exp 对齐。
    expires_at = Column(DateTime(), nullable=False, index=True)
    #: 吊销时间；非空表示该 jti 已失效。
    revoked_at = Column(DateTime(), nullable=True)
    #: 轮换后指向新 jti（审计/追踪用）。
    replaced_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(), default=utcnow, nullable=False)
    #: 可选的客户端元信息，便于入侵排查。
    user_agent = Column(String(512), nullable=True)
    ip_address = Column(String(64), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<RefreshToken jti={self.jti} user_id={self.user_id}>"
