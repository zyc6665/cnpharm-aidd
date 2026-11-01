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

    计数后端可选择：
    * ``memory``：进程内缓存，仅适合单实例开发环境；
    * ``redis``：多 worker / 多实例共享计数（生产必须使用）。

    计数后端不可用时的行为由 ``fail_mode`` 控制：``closed`` 直接返回 503，
    避免「限流器坏了就等于不限流」；``open`` 仅建议本地开发使用。
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
        backend: str = "memory",
        fail_mode: str = "open",
        redis_cache_client=None,
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.trust_proxy_headers = trust_proxy_headers
        self.backend = backend
        self.fail_mode = fail_mode
        if backend == "redis":
            if redis_cache_client is not None:
                self.cache = redis_cache_client
            else:
                # 延迟导入：只有选择 Redis 计数时才要求安装/连接 redis。
                from app.cache.redis_backend import RedisCacheBackend

                self.cache = RedisCacheBackend()
        else:
            self.cache = cache_client

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        key = self._get_rate_limit_key(request)
        try:
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
        except Exception as exc:
            if self.fail_mode == "closed":
                logger.error(
                    "Rate limit backend unavailable (%s); rejecting request: %s",
                    self.backend,
                    exc,
                )
                return JSONResponse(
                    status_code=503,
                    content={
                        "code": 50301,
                        "message": "Rate limit service unavailable",
                        "data": None,
                    },
                    headers={"Retry-After": "5"},
                )
            logger.warning(
                "Rate limit backend unavailable (%s); failing open: %s",
                self.backend,
                exc,
            )

        return await call_next(request)

    def _get_rate_limit_key(self, request: Request) -> str:
        client_ip = request.client.host if request.client else "unknown"
        if self.trust_proxy_headers:
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                client_ip = forwarded_for.split(",", 1)[0].strip()
        return f"rate_limit:ip:{client_ip}"

    async def _is_rate_limited(self, key: str) -> bool:
        """读取当前计数；后端异常向上抛出，由 dispatch 按 fail_mode 决策。"""
        count = await self.cache.get(key)
        return count is not None and int(count) >= self.requests_per_minute

    async def _increment_counter(self, key: str) -> None:
        current = await self.cache.incr(key)
        if current == 1:
            await self.cache.expire(key, 60)
