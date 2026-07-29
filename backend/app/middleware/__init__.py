# backend/app/middleware/__init__.py
"""中间件模块。"""

from app.middleware.rate_limit import RateLimitMiddleware

__all__ = ["RateLimitMiddleware"]
