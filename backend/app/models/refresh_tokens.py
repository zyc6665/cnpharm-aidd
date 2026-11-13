# backend/app/models/refresh_tokens.py
"""Refresh Token 持久化模型（jti 存储 / 轮换 / 复用检测）。

设计要点（docs/archive/22 P2 认证授权）：
* refresh token 仍是无状态 JWT，但签发的每个 ``jti`` 都会落库一行；
* 轮换时旧 jti 标记 ``revoked_at`` 并写 ``replaced_by``，新 jti 另起一行；
* 已吊销的 jti 再次出现即视为「复用入侵」，吊销该用户全部 refresh；
* access token 不落库，保持短寿命；
* 统一身份认证（甲方 IAM）的票据挂在**同一行**上：平台会话与统一票据同生共死，
  轮换/吊销天然是一个事务，不会出现「Cookie 是新 jti、库里是旧票据」的撕裂。

时间列沿用全仓约定：naive UTC（见 ``app.common.time.utcnow``）。
"""

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

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

    # ---- 统一身份认证（IAM）票据：与平台会话同一行，全部可空以兼容历史行 ----
    #: IAM accessToken 的密文（``encrypt_secret()`` 结果，永不下发前端）。
    iam_access_token_enc = Column(Text, nullable=True)
    #: IAM refreshToken 的密文（``encrypt_secret()`` 结果，永不下发前端）。
    iam_refresh_token_enc = Column(Text, nullable=True)
    #: IAM accessToken 的过期时间（naive UTC），用于判断是否需要提前续期。
    iam_access_expires_at = Column(DateTime(), nullable=True)
    #: 最近一次 IAM 校验**成功**的时间，也是「IAM 不可达时宽限放行」的锚点。
    #: 注意：不可达但宽限放行时**不得**刷新该列，否则故障期会无限期放行。
    iam_checked_at = Column(DateTime(), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<RefreshToken jti={self.jti} user_id={self.user_id}>"
