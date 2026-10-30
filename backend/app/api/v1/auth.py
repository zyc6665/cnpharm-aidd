# backend/app/api/v1/auth.py
"""认证API

登录标识从 email 改为 **username**；认证源由 ``User.auth_source`` 决定：

* ``local``：``verify_password(password, user.password_hash)``；
* ``ldap``：调用 ``get_ldap_authenticator()`` 校验企业目录，成功后回填 ``ldap_dn`` /
  ``last_login_at``，绝不落本地口令。

公开注册已移除；邮箱验证码/自助重置等链路统一停用（HTTP 403 + 业务码 40002）。
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.database.session import get_db
from app.models.users import User, UserStatus
from app.auth.jwt_handler import JWTHandler
from app.auth.password import verify_password
from app.auth.dependencies import get_current_user
from app.auth.ldap_provider import LdapAuthenticator, get_ldap_authenticator
from app.schemas.users import UserLogin, UserResponse
from app.schemas.verification import PasswordResetRequest
from app.common.responses import success_response
from app.common.exceptions import BusinessException, UnauthorizedException
from app.common.time import utcnow
from app.logging.audit import AuditResult, get_audit_logger

router = APIRouter()
jwt_handler = JWTHandler()

#: 统一登录失败文案：不泄露用户是否存在/认证源/是否禁用。
_LOGIN_FAILED_MESSAGE = "用户名或密码错误"
_DISABLED_MESSAGE = "该功能已停用，请联系管理员"


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
    db: AsyncSession = Depends(get_db),
    authenticator: LdapAuthenticator | None = Depends(get_ldap_authenticator),
):
    """用户登录（username + 口令）。"""
    client_ip, user_agent = _client_meta(request)
    audit = get_audit_logger()

    username = (login_data.username or "").strip()

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

    audit.log_login(
        user_id=str(user.id),
        email=user.email,
        username=user.username,
        result=AuditResult.SUCCESS,
        client_ip=client_ip,
        user_agent=user_agent,
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
    refresh_token: str,
    db: AsyncSession = Depends(get_db),
):
    """刷新令牌"""
    try:
        payload = jwt_handler.verify_token(refresh_token, token_type="refresh")
    except Exception:
        raise UnauthorizedException("无效的刷新令牌")

    user_id = payload.get("sub")

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

    return success_response(
        data={
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
        },
        message="令牌刷新成功",
    )


@router.post("/logout", response_model=dict)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """登出（客户端清除令牌即可）"""
    client_ip, user_agent = _client_meta(request)
    get_audit_logger().log_logout(
        user_id=str(current_user.id),
        client_ip=client_ip,
        user_agent=user_agent,
    )
    return success_response(message="登出成功")
