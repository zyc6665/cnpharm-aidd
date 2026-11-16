# backend/app/api/v1/auth_sso.py
"""统一身份认证（IAM）单点登录。

浏览器视角只有两步，两次都是**顶层页面跳转**：

    GET /api/v1/auth/sso/authorize   -> 302 到甲方登录页（带 state）
    GET /api/v1/auth/sso/callback    -> 换票、认人/开户、写平台 Cookie、303 回前端

设计要点
--------
* **失败一律 303 回登录页**，带 ``sso_error=<码>`` 让前端翻译成人话。这两个端点都由
  浏览器直接导航，返回 JSON 信封或 500 只会让用户看到一个白屏错误页。
* **state 放 HttpOnly Cookie，且值带服务端 HMAC**：回跳时先验签、再与 query 里的
  state 做恒定时间比对。不放服务端存储：单点登录是低频操作，不值得为它引入一张表。
  这枚 Cookie 为 host-only（不设 Domain）——同注册域的兄弟应用若能种 Cookie，就能
  种下一对合法签名，仅靠签名挡不住登录 CSRF（残余风险，见任务单备注）。Cookie 的
  SameSite 至少是 ``lax``——从甲方域名跳回来是顶层 GET，``strict`` 会让 Cookie 完全
  不发送，回跳必然失败。
* **回跳目标也只从 Cookie 读**，不信 URL 里的 next：否则
  ``/authorize?next=https://evil.example`` 就是一个开放重定向。
* **账号对应先认 sso_uid 再认用户名**。同名本地账号不会被自动接管——否则任何能拿到
  甲方会话的人都能顶掉平台的管理员账号。这类冲突要让管理员显式处理。
* 不用再单独调 ``checkAccessToken`` 自检：``getUserInfo`` 对失效票据本来就回
  ``2002``，多一次往返只是多一个失败面。``checkAccessToken`` 留给刷新链路用。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from typing import Any, Optional
from urllib.parse import quote, unquote, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import (
    ACCESS_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    generate_csrf_token,
    set_auth_cookies,
)
from app.auth.dependencies import enforce_csrf
from app.auth.jwt_handler import JWTHandler
from app.common.exceptions import BusinessException
from app.common.request_meta import client_meta
from app.common.responses import success_response
from app.common.time import utcnow
from app.config import settings
from app.database.session import get_db
from app.logging.audit import AuditResult, get_audit_logger
from app.models.users import AuthSource, User, UserStatus
from app.services.iam_client import IamClient, IamError, IamToken, IamUser, get_iam_client
from app.services.iam_session import seal_tickets
from app.services.refresh_token_store import (
    clear_iam_tickets,
    expires_at_from_payload,
    revoke_refresh_token,
    store_refresh_token,
)

logger = logging.getLogger(__name__)

router = APIRouter()
jwt_handler = JWTHandler()

#: state 与回跳目标存在同一枚 HttpOnly Cookie 里，值形如
#: ``<state>|<编码后的目标>|<HMAC-SHA256 hex>``；目标一并签名，防止被改写。
#: Path 收窄到本组路由，且**不设 Domain**（host-only）：同注册域的兄弟应用若能往
#: 本域种 Cookie，就能种下一对「合法」的 state+签名，登录 CSRF 依然成立。
SSO_STATE_COOKIE_NAME = "cpumodel_sso_state"
SSO_STATE_COOKIE_PATH = "/api/v1/auth/sso"

#: 签名域前缀：与 JWT（HS256）、文件下载令牌的签名分开，避免跨协议签名复用。
_STATE_SIGNATURE_CONTEXT = b"sso-state-v1:"

AUTHORIZE_PATH = "/api/v1/auth/sso/authorize"
LOGIN_PAGE = "/login"

#: 回跳 URL 里允许出现的公开错误码，与 ``frontend/src/utils/sso.ts`` 的
#: ``SSO_ERROR_CODES`` 一一对应。**不要新增**：前端没有对应的翻译，用户只会看到
#: 一个原始 key；「为什么失败」写进审计，不写进 URL。
_FAIL_PUBLIC_CODES = frozenset(
    {
        "disabled",
        "state",
        "denied",
        "token",
        "userinfo",
        "unavailable",
        "conflict",
        "inactive",
        "not_provisioned",
    }
)

#: 用户名允许的字符集，与 ``derive_username_from_email`` 保持一致的规则。
_USERNAME_INVALID_CHARS = re.compile(r"[^A-Za-z0-9._-]")
#: 与 ``users.username`` 的 ``String(64)``、管理员建号的 ``{1,64}`` 对齐。
#: 曾经是 56：预建的 57~64 字符账号名永远撞不上、也永远登不进去（D-07）。
_USERNAME_MAX_LENGTH = 64


# --------------------------------------------------------------------- 小工具
def _login_error_url(error: str) -> str:
    return f"{LOGIN_PAGE}?sso_error={quote(error, safe='')}"


def _redirect(url: str, *, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=status_code)


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _log_safe(value: Optional[str], *, limit: int = 120) -> str:
    """外部可控值进日志前去掉控制字符并截断：``%0d%0a`` 能伪造整行日志。"""
    if not value:
        return "-"
    return _CONTROL_CHARS.sub("?", value)[:limit]


def _exception_summary(exc: BaseException, *, limit: int = 80) -> str:
    """把意外异常压成「类型名 + 首行摘要」，专供日志。

    为什么不能直接写 ``str(exc)``：C-02 兜底分支捕获的是 IAM 客户端内部异常，其中
    pydantic 的 ``ValidationError`` 会把**入参原值**写进消息——形如::

        1 validation error for TokenResponse
        access_token
          Input should be a valid string [type=string_type, input_value='<令牌原文>']

    直接回显就等于把 token / 授权码写进日志。这里只取**首行**再经 ``_log_safe`` 净化、
    截断：凭据在 pydantic 的格式里总落在后续行，只留首行就已经把它挡在外面；同时保留
    了「哪一层炸了、炸成什么类型」这两项排障必需的信息。
    """
    message = str(exc).strip()
    head = message.splitlines()[0] if message else ""
    summary = _log_safe(head, limit=limit)
    return type(exc).__name__ if summary == "-" else f"{type(exc).__name__}: {summary}"


#: 回跳目标的长度上限：超长一律丢弃（**不截断**）。截断会让卡在边界上的越权串
#: 「看起来」合法——旧实现 ``[:512]`` 正是这么放过绕过串的。
_PATH_MAX_LENGTH = 512


def _fully_unquote(value: str) -> Optional[str]:
    """反复 percent-decode（最多 3 轮，解不动就停）；解码异常一律按 ``None``。

    为什么要循环：旧实现只在 ``_read_state_cookie`` 里解**一层**，于是
    ``/%252e%252e/evil`` 解一层后是 ``/%2e%2e/evil``——看上去没有点段。判定要在
    多层编码下仍然成立，所以这里循环解到稳定（最多 3 轮）。

    3 轮的边界说明：浏览器对我们写进 ``Location`` 的值只解**一次**编码，所以
    「解 3 轮后仍含 ``%25``」的输入在浏览器侧本来就等于字面量，不构成越权；这层
    循环是防守式的宽进严出，不是模拟浏览器的递归解码。更深的编码（≥6 层）会落到
    「规范化后作为字面路径使用」，与站内路径的语义一致。
    """
    current = value
    for _ in range(3):
        try:
            decoded = unquote(current)
        except (TypeError, UnicodeError, ValueError):
            return None
        if decoded == current:
            break
        current = decoded
    return current


def _safe_local_path(value: Optional[str]) -> Optional[str]:
    """只接受站内绝对路径，挡掉 ``//evil.example``、``https://...``、点段越权、换行注入。

    返回 ``None`` 表示「不是可用的站内路径」，调用方回落到默认页。
    """
    if not value:
        return None
    candidate = value.strip()
    if len(candidate) > _PATH_MAX_LENGTH:
        return None
    decoded = _fully_unquote(candidate)
    if decoded is None:
        return None
    decoded = decoded.strip()
    if len(decoded) > _PATH_MAX_LENGTH:
        return None
    # 既有拒绝规则，作用在**解码后**的字符串上：非站内绝对路径、协议相对地址
    # ``//host``、反斜杠（浏览器把反斜杠也当分隔符，``/\evil.example`` 因此同样是
    # 站外跳转）、控制字符（``\r\n`` 能注入响应头）。
    if not decoded.startswith("/") or decoded.startswith("//"):
        return None
    if "\\" in decoded or _CONTROL_CHARS.search(decoded):
        return None
    # 点段判定：以 ``/`` 切分（反斜杠上面已拒绝，这里仍按分隔符再切一次做双保险），
    # 任何一段是 ``.`` 或 ``..`` 就整条丢弃。不做「消解 ../」的补救：浏览器对
    # ``/a/..%2fb`` 的归一是 ``/b``，与我们的目录树不一致，消解等于替攻击者选目标。
    segments: list[str] = []
    for segment in re.split(r"[/\\]", decoded):
        if segment in (".", ".."):
            return None
        if segment:
            segments.append(segment)
    # 归一化只用字符串拼接，**不用** ``os.path.normpath``：后者在 Windows 上输出反斜杠，
    # 会把合法路径改名（``/a/b`` -> ``\a\b``），也会把 ``//host`` 折成 ``\\host``，
    # 让「判定」和「输出」用上两套分隔符。
    normalized = "/" + "/".join(segments)
    # 末了再对**归一化结果**做一次断言式校验（只看路径部分，querystring 里出现 ".."
    # 是合法的，例如 ``/tasks?range=1..2``）。这样即便将来有人改了上面的切分逻辑，
    # 「返回值必须是站内绝对路径且路径段里没有点段」这条不变量也不会被绕过——判定标准
    # 应该落在最终要拿去跳转的那个字符串上，而不是中间产物。
    path_only = normalized.split("?", 1)[0].split("#", 1)[0]
    if not normalized.startswith("/") or ".." in path_only:
        return None
    if len(normalized) > _PATH_MAX_LENGTH:
        return None
    return normalized


def _states_match(stored: Optional[str], received: Optional[str]) -> bool:
    """恒定时间比对 state；非 ASCII / 编码异常一律视为不匹配。

    ``secrets.compare_digest`` 的 str 版本只接受 ASCII：query 里出现非 ASCII
    （``?state=%E4%B8%AD``）会抛 ``TypeError``，把回跳打成 500 白屏页，违反
    「失败一律 303」的契约。这里统一按 UTF-8 字节比较。
    """
    if not stored or not received:
        return False
    try:
        return secrets.compare_digest(stored.encode("utf-8"), received.encode("utf-8"))
    except (AttributeError, TypeError, UnicodeError):
        return False


def _state_secret() -> Optional[bytes]:
    """签名 state 的密钥：由 ``JWT_SECRET_KEY`` 派生，运行期读取。"""
    secret = (settings.JWT_SECRET_KEY or "").strip()
    return secret.encode("utf-8") if secret else None


def _state_signature(payload: str, *, secret: bytes) -> str:
    return hmac.new(
        secret, _STATE_SIGNATURE_CONTEXT + payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _state_cookie_value(state: str, target: str) -> str:
    """``<state>|<编码后目标>|<HMAC-SHA256 hex>``；目标一并签名，防止被改写。"""
    payload = f"{state}|{quote(target, safe='')}"
    secret = _state_secret()
    if secret is None:  # 无密钥：写一个必然验不过的值（fail closed）
        return payload
    return f"{payload}|{_state_signature(payload, secret=secret)}"


def _split_state_cookie(raw: Optional[str]) -> Optional[tuple[str, str]]:
    """验签并拆出 ``(state, 编码后的目标)``；缺字段/签名不符返回 ``None``。"""
    if not raw:
        return None
    parts = raw.split("|")
    if len(parts) != 3:
        return None
    state, encoded_target, signature = parts
    secret = _state_secret()
    if not state or not secret:
        return None
    expected = _state_signature(f"{state}|{encoded_target}", secret=secret)
    if not _states_match(expected, signature):  # 复用同一套字节比对，避免同类 TypeError
        return None
    return state, encoded_target


def _state_samesite() -> str:
    """回跳 Cookie 的 SameSite。

    从甲方域名跳回平台是跨站的顶层导航：``strict`` 会让浏览器直接不发这枚 Cookie，
    回跳一定失败，因此 ``strict`` 时降级为 ``lax``。
    """
    return "lax" if settings.COOKIE_SAMESITE == "strict" else settings.COOKIE_SAMESITE


# A-06（已知限制，本轮明确不修）：state 是**单槽** Cookie——每次 ``/authorize`` 都
# 覆盖同一枚 ``cpumodel_sso_state``，回调成功即删除。后果是「同一个回跳页被打开两次」
# （双击、后退后刷新、两个标签页各点一次登录）第二次必然 ``sso_error=state``：第一次
# 已经把 Cookie 用掉了。判定为**可接受降级**：再点一次登录即可恢复，CSRF 校验强度
# 一点没降。改成多槽需要把 Cookie 值升级成「state 列表」的编码格式（每条带自己的
# 过期时间），签名覆盖范围与清 Cookie 逻辑都要跟着改，收益不抵复杂度。当前行为由
# ``test_state_cookie_single_slot_second_use_is_rejected`` 固定，避免以后被无意「修好」。
def _set_state_cookie(response: RedirectResponse, state: str, target: str) -> None:
    response.set_cookie(
        key=SSO_STATE_COOKIE_NAME,
        value=_state_cookie_value(state, target),
        max_age=settings.SSO_STATE_TTL_SECONDS,
        httponly=True,
        samesite=_state_samesite(),
        path=SSO_STATE_COOKIE_PATH,
        secure=settings.COOKIE_SECURE,
    )


def _clear_state_cookie(response: RedirectResponse) -> None:
    # 删除时的属性必须与写入一致（path/secure/samesite/httponly），否则删不掉。
    response.delete_cookie(
        key=SSO_STATE_COOKIE_NAME,
        path=SSO_STATE_COOKIE_PATH,
        httponly=True,
        samesite=_state_samesite(),
        secure=settings.COOKIE_SECURE,
    )


async def _fail(
    db: Optional[AsyncSession],
    request: Optional[Request],
    public: str,
    reason: str,
    *,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    email: Optional[str] = None,
    **extra: Any,
) -> RedirectResponse:
    """统一认证失败路径的**唯一出口**：回滚 -> 审计 -> 日志 -> 清 state Cookie -> 303。

    为什么要收口：修复前 9 类失败里只有「同名冲突」写了审计，state 校验失败 /
    用户拒绝授权 / 换票失败 / 取用户信息失败 / 开户失败全是 ``logger.warning``。
    出事时既查不到是谁，也没有稳定的原因字段可供告警规则匹配。收口之后「有没有
    审计」不再依赖每个分支的自觉——新增分支只要走 ``_fail`` 就自动有审计。

    两类信息严格分层，不要混：

    * ``public``：进 URL 的公开码，只能是 :data:`_FAIL_PUBLIC_CODES` 里的 9 个；
    * ``reason`` / ``extra``：只进审计与日志（阶段名、IAM 返回码、分支名、sso_uid…），
      **绝不**进 URL 或响应体。token、授权码 ``code``、state 原文一律不传进来。

    顺序是刻意的——先 ``rollback`` 再审计：开户/落库失败时事务里可能留着半截账号
    （A-02），而 ``database/session.py`` 的 ``get_db`` 在 ``yield`` 之后**无条件
    commit**，不先回滚就会把半成品账号落库。

    本函数自身**不允许抛异常**：它已经是失败路径的最后一站，再抛就只剩 500 白屏。
    """
    if public not in _FAIL_PUBLIC_CODES:
        # 码写错了既不能让用户看到原始 key，也不能让回调 500：降级后继续收口。
        logger.error("统一认证失败码不在白名单 public=%s reason=%s", public, reason)
        public = "unavailable"

    if db is not None:
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001 - 收口函数本身不允许抛异常
            logger.warning("统一认证失败收口回滚事务失败 reason=%s", reason, exc_info=True)

    client_ip, user_agent = client_meta(request)
    # 外部可控值（IAM 返回的文本、iam_code、sso_uid）进日志前一律净化：``%0d%0a``
    # 能把一条日志伪造出两行，审计/日志都会被污染。
    stage = _log_safe(extra.get("stage"))
    iam_code = _log_safe(extra.get("iam_code"))
    branch = _log_safe(extra.get("branch"))
    sso_uid = _log_safe(extra.get("sso_uid"))
    error_text = _log_safe(extra.get("error_text"))
    # ``error_text`` 只进**日志**，不进审计：它是甲方返回的原文（IAM 的 message 可能
    # 把请求参数回显出来，含授权码/票据）。审计要的是可聚合的 ``reason`` + ``iam_code``，
    # 不需要自由文本；日志留给排障，且已过 ``_log_safe`` 净化与截断。
    audit_extra: dict[str, Any] = {
        key: (_log_safe(value) if isinstance(value, str) else value)
        for key, value in extra.items()
        if key != "error_text"
    }

    try:
        get_audit_logger().log_login(
            user_id=user_id,
            email=email,
            username=_log_safe(username) if username else None,
            result=AuditResult.FAILURE,
            client_ip=client_ip,
            user_agent=user_agent,
            reason=reason,
            **audit_extra,
        )
    except Exception:  # noqa: BLE001 - 审计写失败不能把用户卡在回调页
        logger.warning("统一认证失败审计写入失败 reason=%s", reason, exc_info=True)

    logger.warning(
        "统一认证登录失败 stage=%s reason=%s public=%s iam_code=%s branch=%s "
        "sso_uid=%s error=%s client_ip=%s",
        stage,
        reason,
        public,
        iam_code,
        branch,
        sso_uid,
        error_text,
        _log_safe(client_ip),
    )

    response = _redirect(_login_error_url(public))
    _clear_state_cookie(response)
    return response


def _read_state_cookie(raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """验签后拆出 ``(state, target)``；任何异常都退化成 ``(None, None)``。"""
    parsed = _split_state_cookie(raw)
    if parsed is None:
        return None, None
    state, encoded_target = parsed
    # target 在 Cookie 里是 quote 过的：解码统一交给 ``_safe_local_path``（它内部做多轮
    # 解码）。这里再单独 unquote 一次，等于把「解几层」拆成两处各说各话——双编码穿透
    # 就是从这道缝里进来的。
    return state, _safe_local_path(encoded_target)


# ------------------------------------------------------------------ 账号对应
def _normalize_username(raw: Optional[str]) -> Optional[str]:
    value = (raw or "").strip()
    if not value:
        return None
    cleaned = _USERNAME_INVALID_CHARS.sub("_", value)[:_USERNAME_MAX_LENGTH]
    cleaned = cleaned.strip("._-")
    return cleaned or None


def _desired_username(iam_user: IamUser) -> Optional[str]:
    """按 ``SSO_USERNAME_CLAIM`` 取开户用户名，逐级兜底。"""
    if settings.SSO_USERNAME_CLAIM == "employeeNo":
        candidates = [iam_user.employee_no, iam_user.user_name]
    else:
        candidates = [iam_user.user_name, iam_user.employee_no]
    candidates.append((iam_user.email or "").split("@", 1)[0])

    for candidate in candidates:
        normalized = _normalize_username(candidate)
        if normalized:
            return normalized
    # 全都没有时至少退回 userId，保证开户不失败（userId 可能含非法字符，已被替换）。
    return _normalize_username(iam_user.user_id)


def _clip(value: Optional[str], limit: int) -> Optional[str]:
    """IAM 侧字段没有长度约束，落库前按列宽截断（PostgreSQL 会直接报错）。"""
    if value is None:
        return None
    return value[:limit]


def _iam_unit_codes(iam_user: IamUser) -> set[str]:
    """取 IAM 返回的 unitCode 集合（只读内存，不落库）。

    ``orgs`` 不落库是既有口径（docs/03-接口/32-统一身份认证对接方案.md），
    这里也不新增列：每次登录现场算一遍。元素不是 dict 就整条跳过——脏数据不该
    把登录打成 500（``org["unitCode"]`` 会 KeyError）。
    """
    codes: set[str] = set()
    for org in iam_user.orgs or ():
        if not isinstance(org, dict):
            continue
        raw = org.get("unitCode")
        if raw is None:
            continue
        code = str(raw).strip()
        if code:
            codes.add(code)
    return codes


def _ensure_unit_allowed(iam_user: IamUser) -> None:
    """准入白名单（G-01）：对**所有** SSO 登录生效（含已开户/预建/自动开户）。

    空列表 = 不限制（默认，保持既有部署行为）。公开错误码复用 conflict
    （_FAIL_PUBLIC_CODES 冻结，不允许新增码）；内部审计 reason/branch 都是
    unit_not_allowed。判定在 _resolve_user 第一行 ⇒ 拒绝时还没有任何 DB 写。
    """
    allowed = set(settings.SSO_ALLOWED_UNIT_CODES or ())
    if not allowed:
        return
    if _iam_unit_codes(iam_user) & allowed:
        return
    raise _ProvisionError(
        "conflict",
        "该统一认证账号不在本平台开放范围内，请联系管理员",
        branch="unit_not_allowed",
        reason="unit_not_allowed",
    )


async def _find_by_sso_uid(db: AsyncSession, sso_uid: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.sso_uid == sso_uid))
    user = result.scalar_one_or_none()
    if user is not None and user.auth_source != AuthSource.SSO.value:
        # D-06 防线：``uq_users_sso_uid`` 只保证唯一，不保证认证源一致。库里一旦
        # 出现「local 账号带着 sso_uid」（历史上靠手工改库留下的），这个人既能口令
        # 登录又能 SSO 登录，而且 IAM 全局登出传导不到平台。这里按冲突处理，
        # 逼管理员先改认证源，而不是让这条脏数据继续被复用。
        raise _ProvisionError(
            "conflict",
            "该统一身份标识已绑定到非统一认证账号，请联系管理员",
            branch="uid_auth_source_mismatch",
            user=user,
        )
    return user


async def _find_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(
        select(User).where(func.lower(User.username) == username.lower())
    )
    return result.scalar_one_or_none()


def _apply_profile(user: User, iam_user: IamUser) -> None:
    """把统一认证里的资料补到平台账号上。

    只填空缺，不覆盖平台已有值：平台侧可能已经被人改过显示名或邮箱，登录一次就把它
    冲掉会很意外。
    """
    if not user.display_name:
        user.display_name = _clip(iam_user.display_name(), 100)
    if not user.email and iam_user.email:
        user.email = _clip(iam_user.email, 255)


class _ProvisionError(Exception):
    """开户/认人失败，携带公开错误码 + 审计用的分支名与账号快照。

    ``_fail`` 会先 ``rollback``，事务一滚 ORM 对象就不可读——所以账号信息必须在
    **抛出的那一刻**取成字符串快照，否则审计里只剩一个错误码，查不到是谁被拒。
    只有「本地同名接管」这种已经定位到具体账号的场景需要传 ``user=``；其余产生点
    只带分支名（``uid_mismatch`` / ``auto_provision_off`` / ``no_username`` /
    ``provision_race`` / ``inactive_status``）。
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        branch: Optional[str] = None,
        user: Optional[User] = None,
        reason: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.branch = branch
        # 需要独立审计 reason 的分支用；None 走 ``_PROVISION_REASON`` 映射表。
        # 为什么单开一个字段：审计词表被冻结用例用 AST 扫描（``_fail`` 第 4 实参
        # 必须是字符串常量），新原因词从 ``_fail`` 实参走就必然打红那份契约。
        self.reason = reason
        self.user_id = str(user.id) if user is not None and user.id else None
        self.username = user.username if user is not None else None
        self.email = user.email if user is not None else None


def _ensure_active(user: User) -> None:
    """写库**之前**先判状态（A-02）。

    修复前是「先回填 sso_uid / 资料、最后才查 status」：一个已停用用户点一次登录，
    即使 303 打回登录页，``get_db`` 在 yield 之后仍会无条件 commit，
    ``sso_uid`` / ``display_name`` / ``email`` / ``last_login_at`` 全部落库——
    一次失败的登录改掉了生产数据。
    """
    if user.status != UserStatus.ACTIVE.value:
        raise _ProvisionError(
            "inactive", "该账号已被停用，请联系管理员", branch="inactive_status"
        )


#: ``_ProvisionError.code`` -> 审计里的稳定原因词。公开码仍是那 9 个，
#: 「为什么失败」只在审计里区分，不新增前端要翻译的码。
_PROVISION_REASON = {
    "conflict": "account_conflict",
    "inactive": "account_inactive",
    "not_provisioned": "not_provisioned",
}


async def _resolve_user(db: AsyncSession, iam_user: IamUser) -> User:
    """把一次成功的统一认证会话翻译成平台账号（必要时开户）。

    失败一律抛 :class:`_ProvisionError`，由 ``sso_callback`` 交给 ``_fail`` 收口；
    这里**不再自己写审计**，否则同一次失败会记两条。

    状态判定已前移：两条命中分支都在任何写入之前调用 :func:`_ensure_active`，
    并保留「本地同名冲突先于停用判定」的顺序——停用的本地同名账号仍报 conflict，
    不向未认证的访客泄露该账号是否存在/是否停用。

    准入闸（G-01）也在**任何**写入之前，且对已开户账号同样生效：白名单只拦新人
    等于给存量留后门——已开户的人调离授权部门后仍能一直登录。
    """
    _ensure_unit_allowed(iam_user)
    # IAM 侧 userId 没有长度约束，落库按列宽截断（``_clip``）；查询必须用**同一个**
    # 归一化值，否则超长 uid 会「写进去是截断值、再登录按原值查不到」——账号永久自锁，
    # 且症状是「每次登录都新开一个号」这种最难看的形态。
    uid = _clip(iam_user.user_id, 128) or ""
    user = await _find_by_sso_uid(db, uid) if uid else None
    if user is None:
        desired = _desired_username(iam_user)
        existing = await _find_by_username(db, desired) if desired else None
        if existing is not None:
            if existing.sso_uid and existing.sso_uid != uid:
                raise _ProvisionError(
                    "conflict",
                    "用户名已被另一个统一认证账号占用",
                    branch="uid_mismatch",
                )
            if existing.auth_source != AuthSource.SSO.value:
                # 本地/LDAP 账号与统一认证同名：不自动接管，交管理员绑定。
                raise _ProvisionError(
                    "conflict",
                    "该账号已存在平台本地账号，需管理员绑定后再用统一认证登录",
                    branch="local_takeover",
                    user=existing,
                )
            # 管理员预建（sso_uid 为空）：首次登录回填 uid 与资料。
            _ensure_active(existing)
            existing.sso_uid = uid
            _apply_profile(existing, iam_user)
            user = existing
        else:
            if not settings.SSO_AUTO_PROVISION:
                raise _ProvisionError(
                    "not_provisioned",
                    "该统一认证用户尚未开通平台账号",
                    branch="auto_provision_off",
                )
            if not desired:
                raise _ProvisionError(
                    "conflict",
                    "统一认证用户信息里没有可用的账号标识",
                    branch="no_username",
                )
            user = User(
                username=desired,
                password_hash=None,
                auth_source=AuthSource.SSO.value,
                sso_uid=uid,
                display_name=_clip(iam_user.display_name(), 100),
                email=_clip(iam_user.email, 255),
                role=settings.SSO_DEFAULT_ROLE,
                status=UserStatus.ACTIVE.value,
            )
            db.add(user)
            try:
                await db.flush()
            except IntegrityError as exc:  # 并发开户 / 用户名大小写冲突
                await db.rollback()
                raise _ProvisionError(
                    "conflict", "统一认证账号开户冲突，请重试", branch="provision_race"
                ) from exc
            # A-07：username/sso_uid 都来自甲方响应，进日志前必须净化（含 ``%0d%0a``
            # 时能伪造整行日志）。
            logger.info(
                "统一认证首次登录自动开户 username=%s sso_uid=%s",
                _log_safe(user.username),
                _log_safe(user.sso_uid),
            )
    else:
        # 状态判定已前移（A-02）：先判停用，再回填资料。
        _ensure_active(user)
        _apply_profile(user, iam_user)

    return user


async def _issue_session(
    db: AsyncSession,
    user: User,
    *,
    client_ip: Optional[str],
    user_agent: Optional[str],
    iam_token: Optional[IamToken] = None,
) -> tuple[str, str, str]:
    """签发平台自己的会话，返回 ``(access_token, refresh_token, csrf_token)``。

    ``iam_token`` 非空时，把甲方票据加密后挂到**同一行** refresh 上：续期、登出、
    复用检测与平台会话同生共死，不会出现「平台 Cookie 已换新、台上票据还是旧的」。
    甲方没给 refreshToken 时只存 access（access 过期后只能重新登录），只记 user_id。
    """
    access_token = jwt_handler.create_access_token(
        user_id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
    )
    refresh_token = jwt_handler.create_refresh_token(user_id=user.id)
    payload = jwt_handler.decode_token(refresh_token) or {}
    sealed: dict[str, object] = {}
    if iam_token is not None:
        sealed = seal_tickets(
            access_token=iam_token.access_token,
            refresh_token=iam_token.refresh_token,
            expires_in=iam_token.expires_in,
        )
        if not iam_token.refresh_token:
            logger.warning("统一认证未返回 refreshToken user_id=%s", user.id)
    await store_refresh_token(
        db,
        jti=str(payload.get("jti") or ""),
        user_id=str(user.id),
        expires_at=expires_at_from_payload(payload),
        user_agent=user_agent,
        ip_address=client_ip,
        **sealed,
    )
    user.last_login_at = utcnow()
    # CSRF token 必须在 commit **之前**生成：commit 成功之后再抛错（``secrets``/os 层
    # 失败虽罕见，但真会发生）已经没有事务可回滚，会留下「会话行已落库、用户却只拿到
    # 303 失败页」的半截状态——下一次登录还会撞上复用检测被连带吊销。
    csrf_token = generate_csrf_token()
    await db.commit()
    return access_token, refresh_token, csrf_token


# ------------------------------------------------------------------- 端点
@router.get("/status")
async def sso_status():
    """前端用它决定登录页是否显示「统一认证登录」入口。"""
    return success_response(
        data={
            "enabled": bool(settings.SSO_ENABLED),
            "authorize_path": AUTHORIZE_PATH,
            "auto_provision": bool(settings.SSO_AUTO_PROVISION),
        }
    )


@router.get("/authorize")
async def sso_authorize(
    request: Request,
    next: Optional[str] = Query(None, alias="next"),
    client: Optional[IamClient] = Depends(get_iam_client),
):
    """跳转到甲方统一登录页。"""
    if client is None:
        # 与 callback 共用同一出口：入口被拒也要有审计，否则「点登录没反应」查不到人。
        return await _fail(None, request, "disabled", "sso_disabled", stage="authorize")

    state = secrets.token_urlsafe(32)
    target = _safe_local_path(next) or _safe_local_path(settings.SSO_SUCCESS_PATH) or "/"
    response = _redirect(client.build_authorize_url(state), status_code=302)
    _set_state_cookie(response, state, target)
    logger.info(
        "发起统一认证登录 client_ip=%s target=%s",
        client_meta(request)[0],
        _log_safe(target),
    )
    return response


@router.get("/callback")
async def sso_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    client: Optional[IamClient] = Depends(get_iam_client),
):
    """统一认证回跳：换票 -> 认人/开户 -> 发平台会话 -> 回前端。

    失败路径只有一个出口 :func:`_fail`（回滚 + 审计 + 清 state Cookie + 303），
    因此下面每个 ``except`` 都是 ``return await _fail(...)``，不再各自拼响应。
    """
    if client is None:
        return await _fail(None, request, "disabled", "sso_disabled", stage="callback")

    client_ip, user_agent = client_meta(request)
    stored_state, target = _read_state_cookie(request.cookies.get(SSO_STATE_COOKIE_NAME))
    if not _states_match(stored_state, state):
        # 没带 state、过期、或与 Cookie 不符：放弃这次回跳，让用户重新点登录。
        # state 是 CSRF 随机数，不进审计/日志，只记「不匹配」这个事实。
        return await _fail(None, request, "state", "state_mismatch", stage="callback")

    if error:
        return await _fail(
            None, request, "denied", "access_denied", stage="callback", error_text=error
        )
    if not code:
        # 没带 code 也没有 error：回跳被截断或被中间设备改写。公开码仍是 ``denied``
        # （前端 9 码词表不变），但内部 reason 单列 ``malformed_callback``——它和
        # 「用户点了拒绝」的处置完全不同（前者要查链路故障，后者是正常业务动作），
        # 混进同一个原因里，告警既不准也没法计数。
        return await _fail(None, request, "denied", "malformed_callback", stage="callback")

    try:
        token = await client.exchange_code(code)
    except IamError as exc:
        # 不传 ``error_text=str(exc)``：IAM 的 message 可能把请求参数（授权码/票据）
        # 回显，按「原文不进审计」的要求只留 IAM 返回码与传输层标志。
        return await _fail(
            db,
            request,
            "unavailable" if exc.is_transport_error else "token",
            (
                "token_exchange_unavailable"
                if exc.is_transport_error
                else "token_exchange_failed"
            ),
            stage="exchange",
            iam_code=exc.code,
            transport=bool(exc.is_transport_error),
        )
    except Exception as exc:  # noqa: BLE001 - C-02：客户端内部异常不能打成 500 白屏
        # iam_client 是并行批次在改的模块，它抛出的**任何**非 IamError 异常
        # （pydantic ValidationError、TypeError…）都不该让用户看到 500：按「没拿到
        # 可信答复」收口为 unavailable，真实类型只进审计。
        return await _fail(
            db,
            request,
            "unavailable",
            "token_exchange_unexpected",
            stage="exchange",
            error_type=type(exc).__name__,
            error_text=_exception_summary(exc),
        )

    try:
        iam_user = await client.get_user_info(token.access_token)
    except IamError as exc:
        return await _fail(
            db,
            request,
            "unavailable" if exc.is_transport_error else "userinfo",
            (
                "userinfo_unavailable"
                if exc.is_transport_error
                else "userinfo_failed"
            ),
            stage="userinfo",
            iam_code=exc.code,
            transport=bool(exc.is_transport_error),
        )
    except Exception as exc:  # noqa: BLE001 - C-02 兜底，同上
        return await _fail(
            db,
            request,
            "unavailable",
            "userinfo_unexpected",
            stage="userinfo",
            error_type=type(exc).__name__,
            error_text=_exception_summary(exc),
        )

    try:
        user = await _resolve_user(db, iam_user)
    except _ProvisionError as exc:
        return await _fail(
            db,
            request,
            exc.code,
            exc.reason or _PROVISION_REASON.get(exc.code, "account_conflict"),
            stage="provision",
            branch=exc.branch,
            sso_uid=iam_user.user_id,
            user_id=exc.user_id,
            username=exc.username,
            email=exc.email,
        )
    except Exception as exc:  # noqa: BLE001 - 认人链路里的意外异常也不能 500
        return await _fail(
            db,
            request,
            "unavailable",
            "provision_unexpected",
            stage="provision",
            sso_uid=iam_user.user_id,
            error_type=type(exc).__name__,
            error_text=_exception_summary(exc),
        )

    # ``_fail`` 会 rollback，之后 ORM 对象不可读：审计要用的字段先取成字符串。
    audit_user_id = str(user.id)
    audit_username = user.username
    audit_email = user.email
    try:
        access_token, refresh_token, csrf_token = await _issue_session(
            db, user, client_ip=client_ip, user_agent=user_agent, iam_token=token
        )
    except Exception as exc:  # noqa: BLE001 - A-03：落库抖动不能把用户打成 500 白屏
        return await _fail(
            db,
            request,
            "unavailable",
            "session_persist_failed",
            stage="session",
            user_id=audit_user_id,
            username=audit_username,
            email=audit_email,
            error_type=type(exc).__name__,
            error_text=str(exc),
        )

    get_audit_logger().log_login(
        user_id=audit_user_id,
        email=audit_email,
        username=audit_username,
        result=AuditResult.SUCCESS,
        client_ip=client_ip,
        user_agent=user_agent,
        reason="统一认证单点登录",
    )

    response = _redirect(target or "/workspace")
    _clear_state_cookie(response)
    set_auth_cookies(
        response,
        access_token=access_token,
        refresh_token=refresh_token,
        csrf_token=csrf_token,
    )
    return response


# ------------------------------------------------------------------ 登出
def _logout_redirect_url() -> str:
    """统一认证注销后的回跳地址。

    优先用 ``SSO_LOGOUT_REDIRECT_URI``（前后端分域时必须显式配置）；否则由回调地址
    推导同源的 ``/login?sso_logout=1``——推导假设 SPA 与后端同源。
    """
    configured = (settings.SSO_LOGOUT_REDIRECT_URI or "").strip()
    if configured:
        return configured
    parts = urlsplit(settings.SSO_REDIRECT_URI or "")
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}/login?sso_logout=1"
    return "/login?sso_logout=1"


@router.post("/logout")
async def sso_logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    client: Optional[IamClient] = Depends(get_iam_client),
):
    """登出：清理平台会话，并把甲方 GLO 地址交给前端做**顶层跳转**。

    为什么不是 302：axios 跟随跨域 302 时 JS 读不到最终地址，页面也不会离开 SPA，
    甲方的 Cookie 清不掉；而让浏览器直接 GET 本站登出接口又带不了 CSRF 头（登出
    CSRF）。所以拆成「POST 带 CSRF 换 URL」+「前端 window.location.assign」。

    不依赖 ``get_current_user``：access 已过期也必须能登出；jti 从 ``cpumodel_refresh``
    解出（``decode_token`` 不校验过期），解析失败就跳过吊销——登出必须幂等。
    """
    has_auth_cookie = any(
        request.cookies.get(name)
        for name in (ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, CSRF_COOKIE_NAME)
    )
    if not has_auth_cookie:
        # A-04/A-05：三枚 Cookie 一枚都没有 = 本来就是登出态。此时**不校验 CSRF，也不
        # 下发清 Cookie 头**：跨站页面可以不带任何凭据打这个接口，若无条件返回「删
        # Cookie」响应头，就变成了「任意站点都能把用户踢下线」的登出 CSRF。
        return success_response(data={"logout_url": None}, message="登出成功")

    # 只要还剩任意一枚 Cookie，就必须过 CSRF 校验；缺 ``cpumodel_csrf``（A-05）也
    # 走这条——校验必然失败，按同样语义回 403。失败时**不清 Cookie、不吊销会话**：
    # 清 Cookie 本身就是攻击者想要的结果，这里不能替他完成。
    try:
        enforce_csrf(request)
    except HTTPException:
        raise BusinessException("CSRF 校验失败", http_status=403, code=40002) from None

    client_ip, user_agent = client_meta(request)
    user: Optional[User] = None
    # 审计与日志要用的值一律**先快照**：commit/rollback 之后 ORM 对象已经过期
    # （rollback 会 expire 整个 identity map），此时再读 ``user.id`` 会触发同步懒加载
    # -> MissingGreenlet -> 500。而 500 响应里既没有清 Cookie 头、也拼不出 GLO 地址，
    # 用户就彻底退不出去了。``is_sso_user`` / ``user_id`` 都是普通值，事务怎么抖都
    # 不影响后面的分支。
    is_sso_user = False
    user_id: Optional[str] = None
    try:
        token = request.cookies.get(REFRESH_COOKIE_NAME)
        payload = jwt_handler.decode_token(token) if token else None
        if payload and payload.get("type") == "refresh":
            sub = payload.get("sub")
            jti = payload.get("jti")
            if sub:
                user = await db.get(User, str(sub))
                if user is not None:
                    is_sso_user = user.auth_source == AuthSource.SSO.value
                    user_id = str(user.id)
            if jti:
                await revoke_refresh_token(db, str(jti))
                # 行已吊销，clear 只按 jti 过滤，仍能清掉密文。
                await clear_iam_tickets(db, str(jti))
            await db.commit()
    except Exception:  # noqa: BLE001 - 登出必须幂等，清理失败也不能让用户退不出去
        logger.warning("统一认证登出清理本地会话失败 user_id=%s", user_id, exc_info=True)
        try:
            # 回滚本身也可能失败（连接断了，正是上面抛异常的那种场景）；那也必须继续
            # 往下走，把「清 Cookie」的响应头发出去。
            await db.rollback()
        except Exception:  # noqa: BLE001
            logger.warning("统一认证登出回滚事务失败 user_id=%s", user_id, exc_info=True)

    # 分支条件也用快照：``user`` 这时可能是已过期的 ORM 实例，能少碰一次就少碰一次。
    if user_id is not None:
        # 审计是旁路：写日志失败（磁盘满、logger 配置坏）不能把登出打成 500——那样既有
        # 可能已吊销了会话，用户却拿不到响应头，退不出去也清不掉甲方会话。
        try:
            get_audit_logger().log_logout(
                user_id=user_id,
                client_ip=client_ip,
                user_agent=user_agent,
            )
        except Exception:  # noqa: BLE001
            logger.warning("统一认证登出写审计失败 user_id=%s", user_id, exc_info=True)

    logout_url: Optional[str] = None
    if is_sso_user:
        if not settings.SSO_ENABLED or client is None:
            logger.warning(
                "统一认证未启用或配置不完整，仅清理平台会话 user_id=%s", user_id
            )
        else:
            try:
                logout_url = client.build_logout_url(
                    _logout_redirect_url(), redirect_to_login=False
                )
            except Exception:  # noqa: BLE001 - 配置异常只降级为「仅退出平台会话」
                logger.warning(
                    "统一认证登出拼接 GLO 地址失败，降级为仅退出平台 user_id=%s",
                    user_id,
                    exc_info=True,
                )

    clear_auth_cookies(response)
    return success_response(data={"logout_url": logout_url}, message="登出成功")
