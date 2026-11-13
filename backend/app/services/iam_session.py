# backend/app/services/iam_session.py
"""统一身份认证（甲方 IAM）会话票据的表示、加密落库与有效性校验。

设计要点：
* IAM 的 ``accessToken`` / ``refreshToken`` **只存在服务端**，以 Fernet 密文形式挂在
  平台 ``refresh_tokens`` 行上（见 ``app.models.refresh_tokens``），永不下发前端；
* 平台每次 ``/auth/refresh`` 时用本模块判断 IAM 全局会话是否仍然有效：有效则放行，
  过期则尝试用 ``refreshToken`` 续期，明确失效则让平台会话一起结束；
* 判定结果只有四种（``IamSessionStatus``）：有效、已续期、失效、IAM 不可达；
  「不可达」的处置（宽限放行 / 拒绝）由调用方按 ``SSO_OFFLINE_GRACE_SECONDS`` 决定，
  本模块不读配置、不写数据库，纯函数便于单测。

安全约定：任何日志都**不允许**输出票据内容，只记录状态、业务码与异常类型。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Optional

from cryptography.fernet import InvalidToken

from app.common.secret_crypto import decrypt_secret, encrypt_secret
from app.common.time import utcnow
from app.services.iam_client import IamError

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查
    from app.services.iam_client import IamClient

logger = logging.getLogger(__name__)

#: accessToken 提前量：剩余寿命不足该秒数即视为「快过期」，直接走 refreshToken 续期。
IAM_ACCESS_SKEW_SECONDS = 60

#: 票据四个字段与 ``refresh_tokens`` 表列名逐字对应，调用方可直接 ``**sealed``。
IAM_ACCESS_TOKEN_ENC = "iam_access_token_enc"
IAM_REFRESH_TOKEN_ENC = "iam_refresh_token_enc"
IAM_ACCESS_EXPIRES_AT = "iam_access_expires_at"
IAM_CHECKED_AT = "iam_checked_at"

#: 甲方《统一认证接口规范 v1》4.1 错误码表中「用户票据失效」的码。
#:
#: * ``2002``：accessToken 不正确或已过期；
#: * ``1025``：refreshToken 不正确或已过期。
#:
#: 只有这两个码能证明「这名用户的这张票据不能再用」，据此结束平台会话。
_TICKET_INVALID_CODES = frozenset({"2002", "1025"})

#: 同一张错误码表里「平台或对方配置/服务异常」的码（语义见右侧注释）：
#:
#: * ``1005``：appId 非法；
#: * ``1008``：缺少 clientSecret；
#: * ``1009``：appId 与 clientSecret 不匹配；
#: * ``1010``：缺少 code；
#: * ``1012``：缺少 grantType；
#: * ``9002``：参数错误；
#: * ``9100``：系统异常。
#:
#: 这些错误与「用户票据」无关：一次配置事故若按票据失效处理，等于把全员踢下线。
_SYSTEM_ERROR_CODES = frozenset(
    {"1005", "1008", "1009", "1010", "1012", "9002", "9100"}
)


class IamTicketDecryptError(RuntimeError):
    """票据密文无法解密。

    常见原因是 ``SETTINGS_ENCRYPTION_KEY`` 被轮换或密文被手工改写；此时按「票据失效」
    处理（清会话、要求重新登录），而不是抛 500。
    """


@dataclass(frozen=True)
class IamTickets:
    """一行平台会话上挂着的 IAM 票据（已解密的内存形态）。"""

    access_token: Optional[str]
    refresh_token: Optional[str]
    access_expires_at: Optional[datetime]
    checked_at: Optional[datetime]


class IamSessionStatus(str, Enum):
    """IAM 会话校验结果。"""

    #: accessToken 仍有效，平台会话可以照常续期。
    ALIVE = "alive"
    #: accessToken 已过期，但用 refreshToken 换到了新票据。
    REFRESHED = "refreshed"
    #: 票据被甲方明确判定失效（或本地根本没有票据），平台会话必须结束。
    DEAD = "dead"
    #: IAM 不可达（网络/超时/5xx/协议异常），是否放行由调用方按宽限期决定。
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class IamSessionResult:
    """``validate_iam_session`` 的返回值。"""

    status: IamSessionStatus
    #: 校验后的票据：``ALIVE`` 为原票据（``checked_at`` 已更新），``REFRESHED`` 为新票据，
    #: ``DEAD``/``UNAVAILABLE`` 为 ``None``。
    tickets: Optional[IamTickets]
    #: 人类可读的原因，仅用于日志与排障。
    reason: str = ""


def seal_tickets(
    *,
    access_token: str,
    refresh_token: Optional[str],
    expires_in: int,
    now: Optional[datetime] = None,
) -> dict[str, object]:
    """把 IAM 票据加密成可直接写库的列值字典。

    ``expires_in`` 来自甲方 ``getToken`` 响应；``<= 0``（甲方未给或给了异常值）时
    按「立即过期」处理，下次平台续期会直接走 refreshToken 分支，并记一条 warning。
    """
    current = now or utcnow()
    if expires_in and expires_in > 0:
        access_expires_at = current + timedelta(seconds=int(expires_in))
    else:
        access_expires_at = current
        logger.warning("统一认证未返回有效 expires_in，accessToken 按立即过期处理")

    return {
        IAM_ACCESS_TOKEN_ENC: encrypt_secret(access_token),
        IAM_REFRESH_TOKEN_ENC: encrypt_secret(refresh_token) if refresh_token else None,
        IAM_ACCESS_EXPIRES_AT: access_expires_at,
        IAM_CHECKED_AT: current,
    }


def open_tickets(
    *,
    access_token_enc: Optional[str],
    refresh_token_enc: Optional[str],
    access_expires_at: Optional[datetime],
    checked_at: Optional[datetime],
) -> IamTickets:
    """把库里的密文列解密成 ``IamTickets``。

    解密失败统一抛 ``IamTicketDecryptError``，由调用方按「票据失效」处理；任何分支
    都不会把明文写进日志。
    """
    try:
        access_token = decrypt_secret(access_token_enc) if access_token_enc else None
        refresh_token = decrypt_secret(refresh_token_enc) if refresh_token_enc else None
    except InvalidToken as exc:
        raise IamTicketDecryptError("统一认证票据解密失败") from exc

    return IamTickets(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=access_expires_at,
        checked_at=checked_at,
    )


def seal_ticket_columns(tickets: IamTickets) -> dict[str, object]:
    """把（校验/续期后的）票据加密成 ``update_iam_tickets`` 的四个关键字参数。

    只用于「整体覆盖」，与 ``seal_tickets`` 的区别是时间字段直接沿用票据本身，
    不再按 ``expires_in`` 重算。
    """
    return {
        "access_token_enc": (
            encrypt_secret(tickets.access_token) if tickets.access_token else None
        ),
        "refresh_token_enc": (
            encrypt_secret(tickets.refresh_token) if tickets.refresh_token else None
        ),
        "access_expires_at": tickets.access_expires_at,
        "checked_at": tickets.checked_at,
    }


def _classify_iam_error(exc: IamError, phase: str) -> IamSessionResult:
    """把 ``IamError`` 分成「IAM 不可达」与「票据失效」两类。

    判定口径按甲方《统一认证接口规范 v1》4.1 错误码表，顺序匹配：

    1. HTTP 408 / 429 / >=500 → 不可达：限流、超时、服务端故障都是暂时性的，
       按票据失效处理会把一次抖动变成全体重登；
    2. HTTP 401 / 403：
       * ``phase == "check"`` → 不可达。accessToken 过期时 IAM 完全可能直接回
         401/403（而不是业务码 2002），此刻判死会把「续期即可自愈」的用户踢下线；
         调用方 ``validate_iam_session`` 已在 check 阶段拦下这种错误并继续走
         refreshToken 分支——票据真被吊销时续期也会被拒，安全边界没有放宽。
         本函数这里只做兜底，正常流程走不到；
       * ``phase == "refresh"`` → 票据失效：连续期凭证都被拒，说明甲方已吊销会话；
    3. 其它 HTTP 4xx（如 400）→ 不可达：与我们拼的参数有关，不是用户票据的问题；
    4. 传输层失败（``IamError.is_transport_error``，即 ``code is None``，覆盖
       连不上/超时/TLS/响应不是 JSON 以及「既无状态也无业务码」的理论分支）→
       不可达，由调用方按宽限期决定放行还是拒绝；
    5. ``code in _TICKET_INVALID_CODES``（2002/1025）→ 票据失效；
    6. ``code in _SYSTEM_ERROR_CODES``（appId/clientSecret/参数/系统异常）→
       不可达。这些码说明**我们或对方的配置/服务出了问题**，与用户票据无关；
       若按票据失效处理，一次配置事故（比如轮换了 clientSecret 却漏改环境变量）
       就会让所有在线用户被迫重新登录——把用户当成了配置错误的代价；
    7. 其它未知业务码 → 票据失效（fail-closed）。既然无法证明票据仍然有效，就
       宁可要求重新登录；同时必须用 ``logger.error`` 带上 ``phase`` 与 ``code``，
       让甲方新增的错误码在联调时立刻暴露，而不是被静默归入某个已知分支。

    注意：``IamError.is_transport_error`` 的定义是 ``code is None``，HTTP 层的
    错误同样满足它，所以必须先按 ``http_status`` 分流，不能把它放在最前面。
    """
    status = exc.http_status
    if status is not None:
        if status in (408, 429) or status >= 500:
            logger.warning(
                "统一认证暂时不可用 phase=%s http_status=%s", phase, status
            )
            return IamSessionResult(
                IamSessionStatus.UNAVAILABLE, None, f"{phase}_unavailable"
            )
        if status in (401, 403):
            if phase == "check":
                # 兜底：正常流程里 validate_iam_session 已改为继续尝试续期。
                logger.warning(
                    "统一认证校验返回鉴权失败，不直接判死 phase=%s http_status=%s",
                    phase,
                    status,
                )
                return IamSessionResult(
                    IamSessionStatus.UNAVAILABLE, None, f"{phase}_auth_rejected"
                )
            logger.warning(
                "统一认证续期被拒，判定票据失效 phase=%s http_status=%s",
                phase,
                status,
            )
            return IamSessionResult(
                IamSessionStatus.DEAD, None, f"{phase}_http_{status}"
            )
        logger.warning("统一认证返回非预期状态 phase=%s http_status=%s", phase, status)
        return IamSessionResult(
            IamSessionStatus.UNAVAILABLE, None, f"{phase}_unavailable"
        )

    if exc.is_transport_error:
        logger.warning(
            "统一认证不可达 phase=%s error=%s", phase, type(exc).__name__
        )
        return IamSessionResult(
            IamSessionStatus.UNAVAILABLE, None, f"{phase}_unavailable"
        )

    code = str(exc.code)
    if code in _TICKET_INVALID_CODES:
        logger.warning("统一认证判定票据失效 phase=%s code=%s", phase, code)
        return IamSessionResult(IamSessionStatus.DEAD, None, f"{phase}_code_{code}")
    if code in _SYSTEM_ERROR_CODES:
        logger.error(
            "统一认证配置/系统错误，按不可达处理 phase=%s code=%s", phase, code
        )
        return IamSessionResult(
            IamSessionStatus.UNAVAILABLE, None, f"{phase}_unavailable"
        )
    # 未知业务码：fail-closed，且必须用 error 级日志把新码暴露给联调。
    logger.error("统一认证返回未知业务码，按票据失效处理 phase=%s code=%s", phase, code)
    return IamSessionResult(IamSessionStatus.DEAD, None, f"{phase}_code_{code}")


def _expires_at(now: datetime, expires_in: int) -> datetime:
    """按甲方返回的 ``expiresIn`` 计算 access 过期时间；缺失/异常时按立即过期。"""
    if expires_in and int(expires_in) > 0:
        return now + timedelta(seconds=int(expires_in))
    return now


async def validate_iam_session(
    client: "IamClient",
    tickets: IamTickets,
    *,
    now: Optional[datetime] = None,
) -> IamSessionResult:
    """用甲方 IAM 判断平台会话挂着的统一票据是否还能用。

    判定顺序（与任务单一致，不要调整）：

    1. access 与 refresh 都没有 → ``DEAD(missing)``；
    2. access 未过期（剩余寿命 > ``IAM_ACCESS_SKEW_SECONDS``）→ ``checkAccessToken``：
       有效即 ``ALIVE``；对方明确答「无效」（业务码或 HTTP 401/403）则落到 3，
       即先给 refreshToken 一次自愈的机会，不在这里结束会话；
    3. 没有可用的 refreshToken → ``DEAD(access_expired)``；
    4. ``refreshToken`` 续期成功 → ``REFRESHED``；失败则按 ``_classify_iam_error``
       的口径分成「票据失效」「不可达」两类。

    除 check 阶段的 401/403 之外，网络/HTTP 故障都返回 ``UNAVAILABLE``，由调用方按
    宽限期决定放行还是拒绝——本函数不读配置、不碰数据库，也不在任何日志里输出票据内容。
    """
    current = now or utcnow()

    access_token = tickets.access_token or ""
    if not access_token and not tickets.refresh_token:
        return IamSessionResult(IamSessionStatus.DEAD, None, "missing")

    access_usable = bool(
        access_token
        and tickets.access_expires_at is not None
        and tickets.access_expires_at - current
        > timedelta(seconds=IAM_ACCESS_SKEW_SECONDS)
    )

    if access_usable:
        try:
            alive = await client.check_access_token(access_token)
        except IamError as exc:
            if exc.http_status in (401, 403):
                # 甲方可能用 401/403 表示「这张 accessToken 不被认可」，最常见的原因
                # 是它已经过期。不能在这里判死：继续用 refreshToken 续期，续期成功
                # 即自愈；票据真被吊销时续期也会被拒，安全性不受影响。
                logger.warning(
                    "统一认证校验返回 %s，不直接判死，继续尝试续期", exc.http_status
                )
            else:
                return _classify_iam_error(exc, "check")
        else:
            if alive:
                return IamSessionResult(
                    IamSessionStatus.ALIVE,
                    replace(tickets, checked_at=current),
                    "alive",
                )
            # 业务码非 9001：accessToken 过期或不被认可，尝试用 refreshToken 续期。

    if not tickets.refresh_token:
        return IamSessionResult(IamSessionStatus.DEAD, None, "access_expired")

    try:
        renewed = await client.refresh(tickets.refresh_token)
    except IamError as exc:
        return _classify_iam_error(exc, "refresh")

    refreshed = IamTickets(
        access_token=renewed.access_token,
        # 对方可能不返回新 refreshToken；此时沿用旧值（它已被消费，下次续期会失败，
        # 失败即按票据失效处理，不会出现两个有效凭证并存的局面）。
        refresh_token=renewed.refresh_token or tickets.refresh_token,
        access_expires_at=_expires_at(current, renewed.expires_in),
        checked_at=current,
    )
    return IamSessionResult(IamSessionStatus.REFRESHED, refreshed, "refreshed")
