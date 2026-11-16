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

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Optional

from cryptography.fernet import InvalidToken

from app.common.secret_crypto import decrypt_secret, encrypt_secret
from app.common.time import utcnow
from app.services.iam_client import (
    _SESSION_ENDPOINTS,
    IAM_RESULT_CODES,
    IamError,
    IamResultCategory,
    codes_of_category,
    iam_result_category,
)

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

#: 会话判定用的两个派生集合，**只能从 ``iam_client.IAM_RESULT_CODES`` 派生**。
#:
#: 这里不再手写码表：语义、分类、规范出处都在 ``iam_client.IAM_RESULT_CODES`` 里，
#: 本模块只消费 ``category``。新增/调整结果码时改那一张表，不要在这里加字面量。
#:
#: * ``ticket_invalid``（``2002`` accessToken 过期、``1025`` refreshToken 过期、
#:   ``1014`` code 非法，规范 4.1.3.6 / 4.1.4.5 / 4.1.5.5）——票据不能再用，结束会话；
#: * ``request_invalid``（``1001``/``1005``/``1008``/``1009``/``1010``/``1012``/
#:   ``1024``/``2001``/``2006``，规范 4.1.3 ~ 4.1.5 的参数与配置错误）——是我方
#:   请求或配置错了，与用户票据无关，按不可达走宽限，**绝不能判死**；
#: * ``success``（``9001``）与 ``other``（``3002``，GLO 专用）都不判死：
#:   ``other`` 类只可能是「已知但与会话无关」的码，把它当垃圾桶塞新码会直接踢人，
#:   所以 ``other`` 永远返回 UNAVAILABLE 并打 ERROR。
_TICKET_INVALID_CODES = codes_of_category(IamResultCategory.TICKET_INVALID)
_REQUEST_INVALID_CODES = codes_of_category(IamResultCategory.REQUEST_INVALID)


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

    五步顺序即策略，每一步都写进 ``reason`` 便于排障：

    1. HTTP >= 500 / 408 / 429 → 不可达：限流、超时、服务端故障都是暂时性的，
       判死会把一次抖动变成全体重登；
    2. 命中 ``iam_client.IAM_RESULT_CODES`` → 按表里的 ``category``（只有第 ① 步
       没命中时才走到这里，所以表内码在 5xx 上不生效）：``ticket_invalid`` 判死；
       ``request_invalid`` 不可达且 ERROR；``success`` 不可达且 ERROR（见 D1 说明）；
       ``other`` 只在「与会话接口不相交」时按仅注销处理（不可达 + ERROR）；
    3. 有状态码（表外）：``401``/``403`` 时 ``check`` 阶段不可达（accessToken 过期
       时对方完全可能直接回 401/403），``refresh`` 阶段判死（连续期凭证都被拒，
       说明甲方已吊销会话）；其它 ``4xx`` 不可达——那是我们拼的参数有问题；
    4. ``code is None`` → 不可达（连不上/超时/TLS/响应不是 JSON/字段结构不合规）；
    5. 其余（带业务码但表里没有）→ 判死（fail-closed）且打 ERROR。

    不变量（评审先读这一段）：

    * **规范码集合内只变宽松**。相对改造前：``1001``/``1024``/``2001``/``2006``
      由「未知码 DEAD」变为 ``UNAVAILABLE``；``1005``/``1008``/``1009``/``1010``/
      ``1012`` 原本就在系统错误集合里，结论不变；``2002``/``1025`` 仍判死；
      ``1014`` 由「未知码 DEAD」变为显式 ``ticket_invalid``，结论不变。没有任何
      规范码从 UNAVAILABLE 变成 DEAD。
    * **旧代码里那两个非规范码已退出码表**（其中一个只是示例 ``userId`` 的子串，
      被误读成了错误码）。它们不属于规范码集合，删除后按「表外未知码 → DEAD」
      处理，相对改造前是**收紧**；仍在使用它们的测试夹具由并行任务迁移。
    * **``9001`` 不判死**：成功码出现在异常里说明调用方判断写错了，按「意外成功」
      走不可达并打 ERROR（``unexpected_success``），不让一行代码 bug 引发全员重登。
    * **``other`` 类永不为它判死**：当前只有 ``3002``（GLO 专用，缺 url 参数）。
    * **同一 ``code`` 的结论与 ``phase`` 无关**；``phase`` 只影响「没有业务码」的
      401/403 分流与 ``reason`` 前缀。
    * **4xx 上表内码优先于状态码，5xx 相反**：``400 + {"code":"1025"}`` 必须判死，
      不能因为状态码落到宽限；``500 + {"code":"1025"}`` 则先被第 ① 步判成不可用
      （``*_unavailable``），业务码不参与判定——对方服务本身出问题时，体里带什么码
      都不足信。表外码只在 HTTP 200 上 fail-closed 判死。
    * 未知码 fail-closed 是**正确策略**，不得改成宽限。
    """
    status = exc.http_status

    # ① 对方服务端故障 / 限流：暂时性。
    if status is not None and (status >= 500 or status in (408, 429)):
        logger.warning("统一认证暂时不可用 phase=%s http_status=%s", phase, status)
        return IamSessionResult(
            IamSessionStatus.UNAVAILABLE, None, f"{phase}_unavailable"
        )

    # ② 表内业务码：结论只由 code 决定，与状态码、phase 无关。
    if exc.code is not None:
        code = str(exc.code)
        category = iam_result_category(code)
        if category is IamResultCategory.TICKET_INVALID:
            logger.warning("统一认证判定票据失效 phase=%s code=%s", phase, code)
            return IamSessionResult(
                IamSessionStatus.DEAD, None, f"{phase}_code_{code}"
            )
        if category is IamResultCategory.REQUEST_INVALID:
            logger.error(
                "统一认证请求/配置错误，按不可达处理 phase=%s code=%s", phase, code
            )
            return IamSessionResult(
                IamSessionStatus.UNAVAILABLE, None, f"{phase}_request_error_{code}"
            )
        if category is IamResultCategory.SUCCESS:
            # D1：已知的「成功」不能按未知码 fail-closed，那是调用方的 bug，不是票据的。
            logger.error(
                "统一认证成功码出现在异常路径，按不可达处理 phase=%s code=%s",
                phase,
                code,
            )
            return IamSessionResult(
                IamSessionStatus.UNAVAILABLE, None, f"{phase}_unexpected_success"
            )
        if category is IamResultCategory.OTHER:
            row = IAM_RESULT_CODES[code]
            if row.endpoints.isdisjoint(_SESSION_ENDPOINTS):
                logger.error(
                    "统一认证返回与会话无关的结果码，按不可达处理 phase=%s code=%s",
                    phase,
                    code,
                )
                return IamSessionResult(
                    IamSessionStatus.UNAVAILABLE, None, f"{phase}_logout_only_{code}"
                )
            # 当前没有这种码；真出现也不判死——other 类不是垃圾桶。
            logger.error(
                "统一认证返回语义未定的结果码，按不可达处理 phase=%s code=%s",
                phase,
                code,
            )
            return IamSessionResult(
                IamSessionStatus.UNAVAILABLE, None, f"{phase}_other_{code}"
            )

    # ③ 表外 + 有状态码：只按「哪个阶段、哪种状态」分流。
    if status is not None:
        if status in (401, 403):
            if phase == "check":
                logger.warning(
                    "统一认证校验返回鉴权失败，不直接判死 phase=%s http_status=%s",
                    phase,
                    status,
                )
                return IamSessionResult(
                    IamSessionStatus.UNAVAILABLE, None, "check_auth_rejected"
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
            IamSessionStatus.UNAVAILABLE, None, f"{phase}_http_{status}"
        )

    # ④ 没拿到业务码：传输类失败，或 200 但字段结构不合规。
    if exc.code is None:
        logger.warning("统一认证不可达 phase=%s error=%s", phase, type(exc).__name__)
        return IamSessionResult(
            IamSessionStatus.UNAVAILABLE, None, f"{phase}_unavailable"
        )

    # ⑤ 表外未知业务码：fail-closed，并必须用 ERROR 把新码暴露给联调。
    code = str(exc.code)
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
    budget_seconds: Optional[float] = None,
) -> IamSessionResult:
    """校验统一票据，整段（check + 续期）受 ``budget_seconds`` 总预算约束。

    为什么需要总预算：单次 IAM 调用各有 ``SSO_TIMEOUT_SECONDS``（默认 5 秒），但一次
    续期**最多串行两次**（先 ``checkAccessToken``，必要时再 ``refreshToken``），最坏
    就是 10 秒。这个最坏值必须小于前端并发刷新的 handoff 等待
    （``frontend/src/api/request.ts`` 的 ``REFRESH_HANDOFF_MAX_WAIT_MS = 6000``）：
    否则抢到刷新权的标签页还在等 IAM，落败方已经等满 6 秒，拿着旧 access 重放，
    被 401 踢回登录页——409 竞态修好了，用户照样掉线。超预算按「不可达」处理
    （走宽限期），与超时的归类一致，不对票据做任何推断。
    """
    if not budget_seconds or budget_seconds <= 0:
        return await _validate_iam_session_flow(client, tickets, now=now)
    try:
        async with asyncio.timeout(budget_seconds):
            return await _validate_iam_session_flow(client, tickets, now=now)
    except TimeoutError:
        logger.warning("统一认证会话校验超出总预算 %.1fs，按不可达处理", budget_seconds)
        return IamSessionResult(IamSessionStatus.UNAVAILABLE, None, "budget_exceeded")


async def _validate_iam_session_flow(
    client: "IamClient",
    tickets: IamTickets,
    *,
    now: Optional[datetime] = None,
) -> IamSessionResult:
    """用甲方 IAM 判断平台会话挂着的统一票据是否还能用。

    判定顺序（与任务单一致，不要调整）：

    1. access 与 refresh 都没有 → ``DEAD(missing)``；
    2. access 未过期（剩余寿命 > ``IAM_ACCESS_SKEW_SECONDS``）→ ``checkAccessToken``：
       有效即 ``ALIVE``；对方明确答「无效」（业务码 ``ticket_invalid``，如 2002）则
       落到 3，先给 refreshToken 一次自愈的机会；HTTP 401/403 **且还有 refreshToken**
       时同样继续走续期；401/403 且**没有** refreshToken 则 ``UNAVAILABLE``
       （``check_auth_rejected``，吃宽限），不在这里结束会话；
    3. 没有可用的 refreshToken → 有明确 ``ticket_invalid`` 证据时 ``DEAD
       (check_ticket_invalid)``，否则（access 本地已过期）``DEAD(access_expired)``；
    4. ``refreshToken`` 续期成功 → ``REFRESHED``；失败则按 ``_classify_iam_error``
       的口径分成「票据失效」「不可达」两类。

    除 check 阶段的 401/403 之外（以及 5xx/408/429 这类对方故障），网络/HTTP 故障
    都返回 ``UNAVAILABLE``，由调用方按宽限期决定放行还是拒绝——本函数不读配置、
    不碰数据库，也不在任何日志里输出票据内容。
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

    # check 是否已明确回答「这张 accessToken 不可用」；本地过期等分支保持 False。
    checked_invalid = False
    if access_usable:
        try:
            alive = await client.check_access_token(access_token)
        except IamError as exc:
            if exc.http_status in (401, 403) and tickets.refresh_token:
                # 甲方可能用 401/403 表示「这张 accessToken 不被认可」，最常见的原因
                # 是它已经过期。不能在这里判死：继续用 refreshToken 续期，续期成功
                # 即自愈；票据真被吊销时续期也会被拒，安全性不受影响。
                logger.warning(
                    "统一认证校验返回 %s，不直接判死，继续尝试续期", exc.http_status
                )
            else:
                # 没有 refreshToken 时，check 是唯一证据；401/403 只说明「这次校验
                # 没被接受」，可能是网关抖动或我方 accessToken 拼错，按不可达走宽限，
                # 不能落到下面的 access_expired 直接判死。
                return _classify_iam_error(exc, "check")
        else:
            if alive:
                return IamSessionResult(
                    IamSessionStatus.ALIVE,
                    replace(tickets, checked_at=current),
                    "alive",
                )
            # 对方明确回答票据失效（业务码 ticket_invalid，如 2002）：先看有没有
            # refreshToken 能自愈，没有则在下个分支立刻判死。
            checked_invalid = True

    if not tickets.refresh_token:
        if checked_invalid:
            # 没有 refreshToken，check 又明确答「这张 accessToken 不可用」：
            # 这是唯一能立刻生效的证据，按票据失效结束会话。
            return IamSessionResult(
                IamSessionStatus.DEAD, None, "check_ticket_invalid"
            )
        # accessToken 本地已过期且没有 refreshToken：零出网，直接判死。
        return IamSessionResult(IamSessionStatus.DEAD, None, "access_expired")

    try:
        renewed = await client.refresh(tickets.refresh_token)
    except IamError as exc:
        return _classify_iam_error(exc, "refresh")

    refreshed = IamTickets(
        access_token=renewed.access_token,
        # 规范 4.1.4.5 要求续期必须返回新的 refreshToken；客户端已把「缺失」抛成
        # 传输类错误，走到这里一定拿到了新值，不再沿用已被消费的旧票。
        refresh_token=renewed.refresh_token,
        access_expires_at=_expires_at(current, renewed.expires_in),
        checked_at=current,
    )
    return IamSessionResult(IamSessionStatus.REFRESHED, refreshed, "refreshed")
