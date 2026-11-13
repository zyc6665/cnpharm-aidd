# backend/app/auth/dependencies.py
"""认证依赖函数"""

from __future__ import annotations

import secrets
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database.session import get_db
from app.models.users import User, UserRole
from app.auth.jwt_handler import jwt_handler
from app.auth.cookies import ACCESS_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME

# Bearer Token安全方案
security = HTTPBearer(auto_error=False)

#: 这些方法不改变服务器状态，Cookie 认证时无需 CSRF 校验。
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _resolve_request_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> tuple[Optional[str], bool]:
    """返回 (token, 是否来自 Cookie)。

    优先 ``Authorization: Bearer``；没有时回退到 ``cpumodel_access`` Cookie。
    Bearer 来源 ``from_cookie=False``，从而跳过 CSRF 校验。
    """
    if credentials is not None:
        return credentials.credentials, False
    cookie_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if cookie_token:
        return cookie_token, True
    return None, False


def _enforce_csrf(request: Request) -> None:
    """Cookie 认证的非安全方法必须携带匹配的 ``X-CSRF-Token``。"""
    if request.method.upper() in _SAFE_METHODS:
        return
    header_token = request.headers.get(CSRF_HEADER_NAME)
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if (
        not header_token
        or not cookie_token
        or not secrets.compare_digest(header_token, cookie_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF 校验失败",
        )


def enforce_csrf(request: Request) -> None:
    """公开包装：供不依赖 ``get_current_user`` 的端点复用同一套 CSRF 校验。

    典型场景是 ``POST /api/v1/auth/sso/logout``：它要允许 access 已过期的用户登出，
    因此不能走依赖链，但状态变更方法仍必须校验 CSRF。
    """
    _enforce_csrf(request)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """获取当前认证用户（必须登录）"""
    token, from_cookie = _resolve_request_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if from_cookie:
        _enforce_csrf(request)

    try:
        payload = jwt_handler.verify_token(token, token_type="access")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的Token"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )

    # 从数据库查询用户
    result = await db.execute(
        select(User)
        .options(joinedload(User.statistics))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在"
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )

    return user


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """获取当前用户（可选）"""
    token, from_cookie = _resolve_request_token(request, credentials)
    if not token:
        return None

    if from_cookie:
        _enforce_csrf(request)

    try:
        payload = jwt_handler.verify_token(token, token_type="access")
        user_id = payload.get("sub")
        if not user_id:
            return None
    except ValueError:
        return None

    result = await db.execute(
        select(User)
        .options(joinedload(User.statistics))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user and user.status == "active":
        return user

    return None


async def get_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """获取管理员用户"""
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    return current_user
