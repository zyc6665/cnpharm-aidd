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
    iam_access_token_enc: Optional[str] = None,
    iam_refresh_token_enc: Optional[str] = None,
    iam_access_expires_at: Optional[datetime] = None,
    iam_checked_at: Optional[datetime] = None,
) -> RefreshToken:
    """落库一个新签发的 refresh jti（不 commit，由调用方统一提交）。

    统一身份认证（IAM）票据以密文形式随行落库；非 SSO 登录时四个参数均为
    ``None``，与历史行为一致。
    """
    record = RefreshToken(
        jti=jti,
        user_id=user_id,
        expires_at=expires_at,
        user_agent=(user_agent or None),
        ip_address=(ip_address or None),
        iam_access_token_enc=iam_access_token_enc,
        iam_refresh_token_enc=iam_refresh_token_enc,
        iam_access_expires_at=iam_access_expires_at,
        iam_checked_at=iam_checked_at,
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
    """吊销某用户全部未吊销的 refresh（复用入侵响应）。返回受影响行数。

    同时清空统一身份认证票据密文，缩短凭证在库内的残留窗口。
    """
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(
            revoked_at=utcnow(),
            iam_access_token_enc=None,
            iam_refresh_token_enc=None,
            iam_access_expires_at=None,
            iam_checked_at=None,
        )
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

    统一身份认证票据随会话一起搬家：旧行的四列在同一条 UPDATE 里清空，新行复制
    旧行的值；随后调用方再按 IAM 的校验结果覆盖新行（见 ``update_iam_tickets``）。
    """
    record = await db.get(RefreshToken, old_jti)
    if record is None or record.user_id != user_id:
        return ROTATE_INVALID
    if record.revoked_at is not None:
        return ROTATE_REUSE
    if record.expires_at is not None and record.expires_at <= utcnow():
        return ROTATE_EXPIRED

    # 先取出旧行票据，之后统一交给新行（旧行在同一条 UPDATE 里清空，避免残留）。
    carried = {
        "iam_access_token_enc": record.iam_access_token_enc,
        "iam_refresh_token_enc": record.iam_refresh_token_enc,
        "iam_access_expires_at": record.iam_access_expires_at,
        "iam_checked_at": record.iam_checked_at,
    }

    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == old_jti, RefreshToken.revoked_at.is_(None))
        .values(
            revoked_at=utcnow(),
            replaced_by=new_jti,
            iam_access_token_enc=None,
            iam_refresh_token_enc=None,
            iam_access_expires_at=None,
            iam_checked_at=None,
        )
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
            **carried,
        )
    )
    await db.flush()
    return ROTATE_OK


async def update_iam_tickets(
    db: AsyncSession,
    jti: str,
    *,
    access_token_enc: Optional[str],
    refresh_token_enc: Optional[str],
    access_expires_at: Optional[datetime],
    checked_at: Optional[datetime],
) -> bool:
    """整体覆盖某 jti 上的统一身份认证票据（只对未吊销行生效）。不 commit。"""
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == jti, RefreshToken.revoked_at.is_(None))
        .values(
            iam_access_token_enc=access_token_enc,
            iam_refresh_token_enc=refresh_token_enc,
            iam_access_expires_at=access_expires_at,
            iam_checked_at=checked_at,
        )
    )
    return bool(result.rowcount)


async def touch_iam_checked_at(
    db: AsyncSession, jti: str, checked_at: datetime
) -> bool:
    """只刷新「最近一次校验成功」时间（只对未吊销行生效）。不 commit。

    宽限放行时**不要**调用本函数：锚点一旦滑动，IAM 长期故障就会变成永久放行。
    """
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == jti, RefreshToken.revoked_at.is_(None))
        .values(iam_checked_at=checked_at)
    )
    return bool(result.rowcount)


async def clear_iam_tickets(db: AsyncSession, jti: str) -> bool:
    """清空某 jti 上的统一身份认证票据密文。不 commit。

    只按 ``jti`` 过滤，**不加** ``revoked_at IS NULL``：登出/判死时该行通常已经被
    吊销，带上条件就永远清不掉凭证。
    """
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == jti)
        .values(
            iam_access_token_enc=None,
            iam_refresh_token_enc=None,
            iam_access_expires_at=None,
            iam_checked_at=None,
        )
    )
    return bool(result.rowcount)


async def purge_expired_for_user(db: AsyncSession, user_id: str) -> None:
    """清理某用户已过期且未吊销的记录（维护用，非必需）。"""
    await db.execute(
        delete(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.expires_at <= utcnow(),
            RefreshToken.revoked_at.is_(None),
        )
    )
