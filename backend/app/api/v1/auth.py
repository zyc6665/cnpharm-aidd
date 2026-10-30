# backend/app/api/v1/auth.py
"""认证API

登录标识从 email 改为 **username**；认证源由 ``User.auth_source`` 决定：

* ``local``：``verify_password(password, user.password_hash)``；
* ``ldap``：调用 ``get_ldap_authenticator()`` 校验企业目录，成功后回填 ``ldap_dn`` /
  ``last_login_at``，绝不落本地口令。

公开注册已移除；邮箱验证码/自助重置等链路统一停用（HTTP 403 + 业务码 40002）。
"""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.database.session import get_db
from app.models.users import User, UserStatus
from app.auth.jwt_handler import JWTHandler
from app.auth.password import verify_password
from app.auth.dependencies import get_current_user
from app.auth.cookies import (
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    generate_csrf_token,
    set_auth_cookies,
)
from app.auth.ldap_provider import LdapAuthenticator, get_ldap_authenticator
from app.schemas.users import UserLogin, UserResponse
from app.schemas.verification import PasswordResetRequest
from app.services import login_throttle
from app.services.refresh_token_store import (
    ROTATE_OK,
    ROTATE_REUSE,
    expires_at_from_payload,
    revoke_all_for_user,
    revoke_refresh_token,
    rotate_refresh_token,
    store_refresh_token,
)
from app.common.responses import success_response
from app.common.exceptions import BusinessException, UnauthorizedException
from app.common.time import utcnow
from app.logging.audit import AuditResult, get_audit_logger

router = APIRouter()
jwt_handler = JWTHandler()

#: 统一登录失败文案：不泄露用户是否存在/认证源/是否禁用。
_LOGIN_FAILED_MESSAGE = "用户名或密码错误"
_DISABLED_MESSAGE = "该功能已停用，请联系管理员"


class RefreshTokenRequest(BaseModel):
    """刷新请求体：字段可选，兼容 Cookie 模式下的空 body。"""

    refresh_token: str | None = None


def _client_meta(request: Request | None) -> tuple[str | None, str | None]:
    """从请求里取 (client_ip, user_agent)，审计事件用。"""
    if request is None:
        return None, None
    client = getattr(request, "client", None)
    ip = getattr(client, "host", None) if client else None
    headers = getattr(request, "headers", None)
    user_agent = headers.get("user-agent") if headers is not None else None
    return ip, user_agent


def _login_failed() -> BusinessException:
    """统一 401 错误（信封业务码 40101，HTTP 401）。"""
    return BusinessException(_LOGIN_FAILED_MESSAGE, http_status=401, code=40101)


@router.post("/login", response_model=dict)
async def login(
    login_data: UserLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    authenticator: LdapAuthenticator | None = Depends(get_ldap_authenticator),
):
    """用户登录（username + 口令）。"""
    client_ip, user_agent = _client_meta(request)
    audit = get_audit_logger()

    username = (login_data.username or "").strip()

    # 账户级锁定：username+IP 连续失败超阈值 -> 429；计数后端不可用 -> 503（fail-closed）。
    await login_throttle.ensure_not_locked(username, client_ip)

    # 大小写不敏感按 username 查用户
    result = await db.execute(
        select(User)
        .options(joinedload(User.statistics))
        .where(func.lower(User.username) == username.lower())
    )
    user = result.scalar_one_or_none()

    if not user:
        audit.log_login(
            user_id=None,
            email=None,
            username=username,
            result=AuditResult.FAILURE,
            client_ip=client_ip,
            user_agent=user_agent,
            reason="用户不存在",
        )
        await login_throttle.register_failure(username, client_ip)
        raise _login_failed()

    if user.status != UserStatus.ACTIVE.value:
        audit.log_login(
            user_id=str(user.id),
            email=user.email,
            username=user.username,
            result=AuditResult.FAILURE,
            client_ip=client_ip,
            user_agent=user_agent,
            reason="账户已被禁用",
        )
        await login_throttle.register_failure(username, client_ip)
        raise _login_failed()

    if user.auth_source == "ldap":
        if authenticator is None:
            audit.log_login(
                user_id=str(user.id),
                email=user.email,
                username=user.username,
                result=AuditResult.FAILURE,
                client_ip=client_ip,
                user_agent=user_agent,
                reason="LDAP 未启用",
            )
            await login_throttle.register_failure(username, client_ip)
            raise _login_failed()

        ldap_result = authenticator.authenticate(username, login_data.password)
        if ldap_result is None:
            audit.log_login(
                user_id=str(user.id),
                email=user.email,
                username=user.username,
                result=AuditResult.FAILURE,
                client_ip=client_ip,
                user_agent=user_agent,
                reason="LDAP 校验失败",
            )
            await login_throttle.register_failure(username, client_ip)
            raise _login_failed()

        # 回填目录 DN 与最近登录时间；不写 password_hash。
        user.ldap_dn = ldap_result.dn
        user.last_login_at = utcnow()
        await db.commit()
    else:
        if not user.password_hash or not verify_password(
            login_data.password, user.password_hash
        ):
            audit.log_login(
                user_id=str(user.id),
                email=user.email,
                username=user.username,
                result=AuditResult.FAILURE,
                client_ip=client_ip,
                user_agent=user_agent,
                reason="密码错误",
            )
            await login_throttle.register_failure(username, client_ip)
            raise _login_failed()

        user.last_login_at = utcnow()
        await db.commit()

    access_token = jwt_handler.create_access_token(
        user_id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
    )
    refresh_token = jwt_handler.create_refresh_token(user_id=user.id)

    # 落库 refresh 的 jti：后续 refresh 走轮换 + 复用检测，logout 可吊销。
    refresh_payload = jwt_handler.decode_token(refresh_token) or {}
    await store_refresh_token(
        db,
        jti=str(refresh_payload.get("jti") or ""),
        user_id=str(user.id),
        expires_at=expires_at_from_payload(refresh_payload),
        user_agent=user_agent,
        ip_address=client_ip,
    )
    await db.commit()

    # 成功登录清零账户级失败计数。
    await login_throttle.reset(username, client_ip)

    audit.log_login(
        user_id=str(user.id),
        email=user.email,
        username=user.username,
        result=AuditResult.SUCCESS,
        client_ip=client_ip,
        user_agent=user_agent,
    )

    # 新契约：httpOnly Cookie + CSRF；body 里的 token 为兼容旧客户端保留（逐步弃用）。
    set_auth_cookies(
        response,
        access_token=access_token,
        refresh_token=refresh_token,
        csrf_token=generate_csrf_token(),
    )

    return success_response(
        data={
            "user": UserResponse.model_validate(user).model_dump(),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        },
        message="登录成功",
    )


@router.post("/reset-password", response_model=dict)
async def reset_password(data: PasswordResetRequest | None = None):
    """邮箱自助重置密码已停用（保留路由，首行拦截）。"""
    raise BusinessException(_DISABLED_MESSAGE, http_status=403, code=40002)


@router.post("/refresh", response_model=dict)
async def refresh_token(
    request: Request,
    response: Response,
    refresh_data: RefreshTokenRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """刷新令牌。

    优先读取 ``cpumodel_refresh`` Cookie；无 Cookie 时回退到 JSON body 的
    ``refresh_token``（旧契约，供 CLI/测试）。响应 body 默认不含 token，仅当请求头
    ``X-Token-Transport: body`` 时返回，便于非浏览器客户端迁移。
    """
    client_ip, user_agent = _client_meta(request)
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not token and refresh_data is not None:
        token = refresh_data.refresh_token

    if not token:
        raise UnauthorizedException("无效的刷新令牌")

    try:
        payload = jwt_handler.verify_token(token, token_type="refresh")
    except Exception:
        raise UnauthorizedException("无效的刷新令牌")

    user_id = payload.get("sub")
    old_jti = payload.get("jti")
    # 旧版未带 jti 的 refresh 无法做吊销/复用检测，按无效处理（强制重新登录）。
    if not user_id or not old_jti:
        raise UnauthorizedException("无效的刷新令牌")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or user.status != UserStatus.ACTIVE.value:
        raise UnauthorizedException("用户不存在或已被禁用")

    new_access_token = jwt_handler.create_access_token(
        user_id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
    )
    new_refresh_token = jwt_handler.create_refresh_token(user_id=user.id)
    new_payload = jwt_handler.decode_token(new_refresh_token) or {}

    rotate_result = await rotate_refresh_token(
        db,
        old_jti=str(old_jti),
        user_id=str(user.id),
        new_jti=str(new_payload.get("jti") or ""),
        new_expires_at=expires_at_from_payload(new_payload),
        user_agent=user_agent,
        ip_address=client_ip,
    )

    if rotate_result == ROTATE_REUSE:
        # 已吊销的 jti 再次使用 = 复用入侵：吊销该用户全部 refresh，强制重新登录。
        await revoke_all_for_user(db, str(user.id))
        await db.commit()
        raise UnauthorizedException("刷新令牌已被使用，请重新登录")
    if rotate_result != ROTATE_OK:
        raise UnauthorizedException("无效的刷新令牌")

    await db.commit()

    set_auth_cookies(
        response,
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        csrf_token=generate_csrf_token(),
    )

    data: dict[str, object] = {"token_type": "bearer"}
    if request.headers.get("X-Token-Transport") == "body":
        data["access_token"] = new_access_token
        data["refresh_token"] = new_refresh_token

    return success_response(data=data, message="令牌刷新成功")


@router.post("/logout", response_model=dict)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    refresh_data: RefreshTokenRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """登出：吊销当前 refresh 的 jti，清理三个认证 Cookie，保留审计。

    Cookie 场景从 ``cpumodel_refresh`` 读取；Bearer/CLI 可把 refresh 放进请求体
    ``refresh_token``（与 /refresh 一致）。access token 不落库、无需吊销。
    """
    client_ip, user_agent = _client_meta(request)
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token and refresh_data is not None:
        refresh_token = refresh_data.refresh_token
    if refresh_token:
        payload = jwt_handler.decode_token(refresh_token) or {}
        jti = payload.get("jti")
        if jti and payload.get("type") == "refresh":
            await revoke_refresh_token(db, str(jti))
            await db.commit()
    get_audit_logger().log_logout(
        user_id=str(current_user.id),
        client_ip=client_ip,
        user_agent=user_agent,
    )
    clear_auth_cookies(response)
    return success_response(message="登出成功")
