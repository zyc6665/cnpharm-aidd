# backend/app/auth/cookies.py
"""认证 Cookie 工具：固定名称、Set-Cookie 属性与 CSRF token。

前端按固定契约读取这几枚 Cookie：
* ``cpumodel_access``：HttpOnly，Path=/，SameSite 取配置（默认 lax）；
* ``cpumodel_refresh``：HttpOnly，Path=/api/v1/auth，SameSite=strict；
* ``cpumodel_csrf``：非 HttpOnly，Path=/，与 access 同 SameSite，前端脚本读取后
  回填 ``X-CSRF-Token`` 请求头。
"""

from __future__ import annotations

import secrets

from fastapi import Response

from app.config import settings

ACCESS_COOKIE_NAME = "cpumodel_access"
REFRESH_COOKIE_NAME = "cpumodel_refresh"
CSRF_COOKIE_NAME = "cpumodel_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"

ACCESS_COOKIE_PATH = "/"
REFRESH_COOKIE_PATH = "/api/v1/auth"
CSRF_COOKIE_PATH = "/"


def generate_csrf_token() -> str:
    """生成不可预测的 CSRF token。"""
    return secrets.token_urlsafe(32)


def _common_kwargs() -> dict[str, object]:
    """Cookie 的公共属性（secure / 可选 domain）。"""
    kwargs: dict[str, object] = {"secure": settings.COOKIE_SECURE}
    if settings.COOKIE_DOMAIN:
        kwargs["domain"] = settings.COOKIE_DOMAIN
    return kwargs


def _refresh_samesite() -> str:
    """refresh Cookie 固定 Strict；跨站（SameSite=none）部署时跟随后端配置。"""
    return "none" if settings.COOKIE_SAMESITE == "none" else "strict"


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
) -> None:
    """登录/刷新成功后一次性写入三个认证 Cookie。"""
    common = _common_kwargs()
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
        path=ACCESS_COOKIE_PATH,
        **common,
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        samesite=_refresh_samesite(),
        path=REFRESH_COOKIE_PATH,
        **common,
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        # CSRF Cookie 是前端判断「是否可能存在会话」的唯一可读信号，
        # 因此其寿命与 refresh Cookie 对齐（否则 access 过期后刷新页面会误判为未登录）。
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        # CSRF Cookie 必须能被前端 JS 读取，因此显式关闭 HttpOnly。
        httponly=False,
        samesite=settings.COOKIE_SAMESITE,
        path=CSRF_COOKIE_PATH,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    """登出时删除三个 Cookie（Path/Domain 必须与设置时一致）。"""
    common = _common_kwargs()
    response.delete_cookie(
        key=ACCESS_COOKIE_NAME,
        path=ACCESS_COOKIE_PATH,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
        **common,
    )
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        samesite=_refresh_samesite(),
        **common,
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path=CSRF_COOKIE_PATH,
        httponly=False,
        samesite=settings.COOKIE_SAMESITE,
        **common,
    )
