# backend/app/services/refresh_token_store.py
"""Refresh Token 的 jti 存储、轮换与复用检测。

调用方（``app/api/v1/auth.py``）在 login 时 ``store_refresh_token``，refresh 时
``rotate_refresh_token``，logout 时 ``revoke_refresh_token``。本模块只负责持久化与
状态判断，不构造 HTTP 响应，便于单测直接验证。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcfromtimestamp, utcnow
from app.models.refresh_tokens import RefreshToken

#: 轮换/校验结果常量。
ROTATE_OK = "ok"
ROTATE_INVALID = "invalid"
ROTATE_EXPIRED = "expired"
ROTATE_REUSE = "reuse"


def expires_at_from_payload(payload: dict) -> datetime:
    """从 JWT payload 的 ``exp`` 解析出 naive UTC 过期时间。

    ``python-jose`` 解码后 ``exp`` 是 Unix 时间戳（int/float）；编码前也可能直接
    拿到 ``datetime``，两种都兼容。
    """
    exp = payload.get("exp")
    if isinstance(exp, datetime):
        return exp.replace(tzinfo=None) if exp.tzinfo is not None else exp
    if exp is None:
        return utcnow()
    return utcfromtimestamp(float(exp))


async def store_refresh_token(
    db: AsyncSession,
    *,
    jti: str,
    user_id: str,
    expires_at: datetime,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> RefreshToken:
    """落库一个新签发的 refresh jti（不 commit，由调用方统一提交）。"""
    record = RefreshToken(
        jti=jti,
        user_id=user_id,
        expires_at=expires_at,
        user_agent=(user_agent or None),
        ip_address=(ip_address or None),
    )
    db.add(record)
    await db.flush()
    return record


async def get_refresh_token(db: AsyncSession, jti: str) -> Optional[RefreshToken]:
    """按 jti 取记录。"""
    return await db.get(RefreshToken, jti)


async def revoke_refresh_token(
    db: AsyncSession, jti: str, *, replaced_by: Optional[str] = None
) -> bool:
    """吊销单个 jti（已吊销则返回 False）。不 commit。"""
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == jti, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow(), replaced_by=replaced_by)
    )
    return bool(result.rowcount)


async def revoke_all_for_user(db: AsyncSession, user_id: str) -> int:
    """吊销某用户全部未吊销的 refresh（复用入侵响应）。返回受影响行数。"""
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    return int(result.rowcount or 0)


async def rotate_refresh_token(
    db: AsyncSession,
    *,
    old_jti: str,
    user_id: str,
    new_jti: str,
    new_expires_at: datetime,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> str:
    """把 ``old_jti`` 轮换成 ``new_jti``。

    返回 ``ROTATE_OK`` 表示成功；``ROTATE_REUSE`` 表示旧 jti 已吊销（疑似复用），
    调用方应吊销该用户全部 refresh 并 401；``ROTATE_INVALID`` / ``ROTATE_EXPIRED``
    分别表示不存在/不属于该用户、已过期。

    并发保护：吊销用条件 UPDATE（``revoked_at IS NULL``），两个并发 refresh 只有
    一个能拿到 ``rowcount == 1``，另一个落到 ``ROTATE_REUSE``。
    """
    record = await db.get(RefreshToken, old_jti)
    if record is None or record.user_id != user_id:
        return ROTATE_INVALID
    if record.revoked_at is not None:
        return ROTATE_REUSE
    if record.expires_at is not None and record.expires_at <= utcnow():
        return ROTATE_EXPIRED

    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == old_jti, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow(), replaced_by=new_jti)
    )
    if not result.rowcount:
        return ROTATE_REUSE

    db.add(
        RefreshToken(
            jti=new_jti,
            user_id=user_id,
            expires_at=new_expires_at,
            user_agent=(user_agent or None),
            ip_address=(ip_address or None),
        )
    )
    await db.flush()
    return ROTATE_OK


async def purge_expired_for_user(db: AsyncSession, user_id: str) -> None:
    """清理某用户已过期且未吊销的记录（维护用，非必需）。"""
    await db.execute(
        delete(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.expires_at <= utcnow(),
            RefreshToken.revoked_at.is_(None),
        )
    )
