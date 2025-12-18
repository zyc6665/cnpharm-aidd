# backend/app/middleware/__init__.py
"""中间件模块"""

from app.middleware.auth_middleware import AuthMiddleware

__all__ = [
    "AuthMiddleware",
]
