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
from typing import Optional
from urllib.parse import quote, unquote, urlsplit

from fastapi import APIRouter, Depends, Query, Request, Response
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

#: 用户名允许的字符集，与 ``derive_username_from_email`` 保持一致的规则。
_USERNAME_INVALID_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_USERNAME_MAX_LENGTH = 56


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


def _safe_local_path(value: Optional[str]) -> Optional[str]:
    """只接受站内绝对路径，挡掉 ``//evil.example``、``https://...``、换行注入。"""
    if not value:
        return None
    candidate = value.strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return None
    if "\\" in candidate or any(ch in candidate for ch in "\r\n\t"):
        return None
    return candidate[:512]


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


def _read_state_cookie(raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """验签后拆出 ``(state, target)``；任何异常都退化成 ``(None, None)``。"""
    parsed = _split_state_cookie(raw)
    if parsed is None:
        return None, None
    state, encoded_target = parsed
    return state, _safe_local_path(unquote(encoded_target))


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


async def _find_by_sso_uid(db: AsyncSession, sso_uid: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.sso_uid == sso_uid))
    return result.scalar_one_or_none()


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
    """开户/认人失败，携带要回给前端的错误码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def _resolve_user(
    db: AsyncSession,
    iam_user: IamUser,
    *,
    client_ip: Optional[str],
    user_agent: Optional[str],
) -> User:
    """把一次成功的统一认证会话翻译成平台账号（必要时开户）。"""
    audit = get_audit_logger()

    user = await _find_by_sso_uid(db, iam_user.user_id)
    if user is None:
        desired = _desired_username(iam_user)
        existing = await _find_by_username(db, desired) if desired else None
        if existing is not None:
            if existing.sso_uid and existing.sso_uid != iam_user.user_id:
                raise _ProvisionError("conflict", "用户名已被另一个统一认证账号占用")
            if existing.auth_source != AuthSource.SSO.value:
                # 本地/LDAP 账号与统一认证同名：不自动接管，交管理员绑定。
                audit.log_login(
                    user_id=str(existing.id),
                    email=existing.email,
                    username=existing.username,
                    result=AuditResult.FAILURE,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    reason="统一认证账号与本地账号同名，拒绝自动接管",
                )
                raise _ProvisionError(
                    "conflict", "该账号已存在平台本地账号，需管理员绑定后再用统一认证登录"
                )
            # 已是 sso 账号但 uid 变了（甲方侧重建用户等）：重新绑定。
            existing.sso_uid = _clip(iam_user.user_id, 128)
            _apply_profile(existing, iam_user)
            user = existing
        else:
            if not settings.SSO_AUTO_PROVISION:
                raise _ProvisionError("not_provisioned", "该统一认证用户尚未开通平台账号")
            if not desired:
                raise _ProvisionError("conflict", "统一认证用户信息里没有可用的账号标识")
            user = User(
                username=desired,
                password_hash=None,
                auth_source=AuthSource.SSO.value,
                sso_uid=_clip(iam_user.user_id, 128),
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
                raise _ProvisionError("conflict", "统一认证账号开户冲突，请重试") from exc
            logger.info(
                "统一认证首次登录自动开户 username=%s sso_uid=%s",
                user.username,
                user.sso_uid,
            )
    else:
        _apply_profile(user, iam_user)

    if user.status != UserStatus.ACTIVE.value:
        raise _ProvisionError("inactive", "该账号已被停用，请联系管理员")
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
    await db.commit()
    return access_token, refresh_token, generate_csrf_token()


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
        logger.warning("统一认证未启用，拒绝 authorize 请求")
        response = _redirect(_login_error_url("disabled"))
        _clear_state_cookie(response)
        return response

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
    """统一认证回跳：换票 -> 认人/开户 -> 发平台会话 -> 回前端。"""
    if client is None:
        response = _redirect(_login_error_url("disabled"))
        _clear_state_cookie(response)
        return response

    client_ip, user_agent = client_meta(request)
    stored_state, target = _read_state_cookie(request.cookies.get(SSO_STATE_COOKIE_NAME))
    if not _states_match(stored_state, state):
        # 没带 state、过期、或与 Cookie 不符：放弃这次回跳，让用户重新点登录。
        logger.warning("统一认证回跳 state 校验失败 client_ip=%s", client_ip)
        response = _redirect(_login_error_url("state"))
        _clear_state_cookie(response)
        return response

    if error or not code:
        logger.info("统一认证回跳带错误 client_ip=%s error=%s", client_ip, _log_safe(error))
        response = _redirect(_login_error_url("denied"))
        _clear_state_cookie(response)
        return response

    try:
        token = await client.exchange_code(code)
    except IamError as exc:
        logger.warning(
            "统一认证换票失败 client_ip=%s code=%s transport=%s",
            client_ip,
            exc.code,
            exc.is_transport_error,
        )
        response = _redirect(_login_error_url("unavailable" if exc.is_transport_error else "token"))
        _clear_state_cookie(response)
        return response

    try:
        iam_user = await client.get_user_info(token.access_token)
    except IamError as exc:
        logger.warning(
            "统一认证取用户信息失败 client_ip=%s code=%s transport=%s",
            client_ip,
            exc.code,
            exc.is_transport_error,
        )
        response = _redirect(
            _login_error_url("unavailable" if exc.is_transport_error else "userinfo")
        )
        _clear_state_cookie(response)
        return response

    try:
        user = await _resolve_user(db, iam_user, client_ip=client_ip, user_agent=user_agent)
    except _ProvisionError as exc:
        logger.warning(
            "统一认证账号对应失败 client_ip=%s sso_uid=%s error=%s",
            client_ip,
            _log_safe(iam_user.user_id),
            exc.code,
        )
        response = _redirect(_login_error_url(exc.code))
        _clear_state_cookie(response)
        return response

    access_token, refresh_token, csrf_token = await _issue_session(
        db, user, client_ip=client_ip, user_agent=user_agent, iam_token=token
    )

    get_audit_logger().log_login(
        user_id=str(user.id),
        email=user.email,
        username=user.username,
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
    if has_auth_cookie:
        enforce_csrf(request)

    client_ip, user_agent = client_meta(request)
    user: Optional[User] = None
    # 先记下认证源：万一后续 commit/rollback 让 ORM 对象过期，也不影响是否拼 GLO。
    is_sso_user = False
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
            if jti:
                await revoke_refresh_token(db, str(jti))
                # 行已吊销，clear 只按 jti 过滤，仍能清掉密文。
                await clear_iam_tickets(db, str(jti))
            await db.commit()
    except Exception:  # noqa: BLE001 - 登出必须幂等，清理失败也不能让用户退不出去
        logger.warning("统一认证登出清理本地会话失败", exc_info=True)
        await db.rollback()

    if user is not None:
        get_audit_logger().log_logout(
            user_id=str(user.id),
            client_ip=client_ip,
            user_agent=user_agent,
        )

    logout_url: Optional[str] = None
    if is_sso_user:
        if not settings.SSO_ENABLED or client is None:
            logger.warning("统一认证未启用或配置不完整，仅清理平台会话 user_id=%s", user.id)
        else:
            logout_url = client.build_logout_url(
                _logout_redirect_url(), redirect_to_login=False
            )

    clear_auth_cookies(response)
    return success_response(data={"logout_url": logout_url}, message="登出成功")
