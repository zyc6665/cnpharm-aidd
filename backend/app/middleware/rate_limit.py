"""全局请求限流中间件。"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """基于客户端 IP 的固定窗口限流。

    限流状态使用项目缓存后端保存。生产环境应配置 Redis，以便多个 API
    实例共享计数；内存缓存仅适用于单实例开发环境。
    """

    EXEMPT_PATHS = {
        "/health",
        # 容器/K8s 探针高频调用，且响应已脱敏，不能被限流误伤（否则探针 429 会触发重启）
        "/api/v1/system/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }

    def __init__(
        self,
        app: ASGIApp,
        cache_client,
        requests_per_minute: int = 60,
        trust_proxy_headers: bool = False,
    ):
        super().__init__(app)
        self.cache = cache_client
        self.requests_per_minute = requests_per_minute
        self.trust_proxy_headers = trust_proxy_headers

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        key = self._get_rate_limit_key(request)
        if await self._is_rate_limited(key):
            return JSONResponse(
                status_code=429,
                content={
                    "code": 42900,
                    "message": "Too many requests, please try again later",
                    "data": None,
                },
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Reset": "60",
                },
            )

        await self._increment_counter(key)
        return await call_next(request)

    def _get_rate_limit_key(self, request: Request) -> str:
        client_ip = request.client.host if request.client else "unknown"
        if self.trust_proxy_headers:
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                client_ip = forwarded_for.split(",", 1)[0].strip()
        return f"rate_limit:ip:{client_ip}"

    async def _is_rate_limited(self, key: str) -> bool:
        try:
            count = await self.cache.get(key)
            return count is not None and int(count) >= self.requests_per_minute
        except Exception as exc:
            logger.warning("Failed to read rate limit counter: %s", exc)
            return False

    async def _increment_counter(self, key: str) -> None:
        try:
            current = await self.cache.incr(key)
            if current == 1:
                await self.cache.expire(key, 60)
        except Exception as exc:
            logger.warning("Failed to increment rate limit counter: %s", exc)
