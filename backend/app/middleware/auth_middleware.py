# backend/app/middleware/auth_middleware.py
"""认证授权中间件

根据详细设计说明书 2.3 节实现。
负责请求的认证检查和权限验证。
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Union
import time
import uuid

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


@dataclass
class AuthInfo:
    """认证信息"""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    is_guest: bool = False
    role: str = "guest"
    permissions: List[str] = None

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []


class AuthMiddleware(BaseHTTPMiddleware):
    """认证授权中间件

    功能：
    1. 检查请求是否需要认证
    2. 验证JWT Token或游客Session
    3. 将认证信息添加到请求状态
    4. 记录请求日志
    """

    # 无需认证的路径（前缀匹配）
    PUBLIC_PATHS: Set[str] = {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/guest",
        "/api/v1/auth/refresh",
        "/api/v1/system/health",
        "/api/v1/system/config",
        "/api/v1/tags",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }

    # 公开但需要可选认证的路径（有认证则使用，无认证则游客）
    OPTIONAL_AUTH_PATHS: Set[str] = {
        "/api/v1/tools",
    }

    # 需要管理员权限的路径
    ADMIN_PATHS: Set[str] = {
        "/api/v1/admin",
    }

    def __init__(
        self,
        app: ASGIApp,
        jwt_handler=None,
        guest_manager=None,
        enable_logging: bool = True
    ):
        """初始化中间件

        Args:
            app: ASGI应用
            jwt_handler: JWT处理器（延迟加载时可为None）
            guest_manager: 游客管理器（延迟加载时可为None）
            enable_logging: 是否启用请求日志
        """
        super().__init__(app)
        self._jwt_handler = jwt_handler
        self._guest_manager = guest_manager
        self.enable_logging = enable_logging

    @property
    def jwt_handler(self):
        """延迟加载JWT处理器"""
        if self._jwt_handler is None:
            from app.auth.jwt_handler import jwt_handler
            self._jwt_handler = jwt_handler
        return self._jwt_handler

    @property
    def guest_manager(self):
        """延迟加载游客管理器"""
        if self._guest_manager is None:
            from app.auth.guest_manager import GuestManager
            self._guest_manager = GuestManager
        return self._guest_manager

    async def dispatch(self, request: Request, call_next):
        """中间件调度

        Args:
            request: 请求对象
            call_next: 下一个处理器

        Returns:
            Response: 响应对象
        """
        start_time = time.time()
        path = request.url.path
        method = request.method

        # 跳过OPTIONS请求（CORS预检）
        if method == "OPTIONS":
            return await call_next(request)

        # 检查是否为公开路径
        if self._is_public_path(path):
            return await call_next(request)

        # 获取认证头
        authorization = request.headers.get("Authorization")
        guest_session = request.headers.get("X-Guest-Session")

        # 验证认证信息
        try:
            auth_info = await self._authenticate(
                authorization=authorization,
                guest_session=guest_session,
                path=path
            )

            # 将认证信息添加到请求状态
            request.state.auth = auth_info

            # 检查管理员权限
            if self._is_admin_path(path) and auth_info.role != "admin":
                return self._forbidden_response("Admin access required")

        except HTTPException as e:
            return self._error_response(e.status_code, e.detail)
        except Exception as e:
            logger.error(f"Authentication error: {e}", exc_info=True)
            return self._error_response(401, "Authentication failed")

        # 执行请求
        response = await call_next(request)

        # 记录请求日志
        if self.enable_logging:
            self._log_request(
                request=request,
                response=response,
                auth_info=auth_info,
                duration=time.time() - start_time
            )

        return response

    def _is_public_path(self, path: str) -> bool:
        """检查是否为公开路径"""
        for public_path in self.PUBLIC_PATHS:
            if path.startswith(public_path):
                return True
        return False

    def _is_optional_auth_path(self, path: str) -> bool:
        """检查是否为可选认证路径"""
        for optional_path in self.OPTIONAL_AUTH_PATHS:
            if path.startswith(optional_path):
                return True
        return False

    def _is_admin_path(self, path: str) -> bool:
        """检查是否为管理员路径"""
        for admin_path in self.ADMIN_PATHS:
            if path.startswith(admin_path):
                return True
        return False

    async def _authenticate(
        self,
        authorization: Optional[str],
        guest_session: Optional[str],
        path: str
    ) -> AuthInfo:
        """验证认证信息

        Args:
            authorization: Authorization头
            guest_session: X-Guest-Session头
            path: 请求路径

        Returns:
            AuthInfo: 认证信息

        Raises:
            HTTPException: 认证失败
        """
        # 优先检查JWT Token
        if authorization:
            if authorization.startswith("Bearer "):
                token = authorization[7:]
                return await self._verify_jwt_token(token)
            else:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid authorization header format"
                )

        # 检查游客Session
        if guest_session:
            return await self._verify_guest_session(guest_session)

        # 可选认证路径允许无认证访问
        if self._is_optional_auth_path(path):
            return AuthInfo(is_guest=True, role="anonymous")

        # 无认证信息
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )

    async def _verify_jwt_token(self, token: str) -> AuthInfo:
        """验证JWT Token

        Args:
            token: JWT Token

        Returns:
            AuthInfo: 认证信息

        Raises:
            HTTPException: Token无效
        """
        try:
            payload = self.jwt_handler.verify_token(token)

            return AuthInfo(
                user_id=payload.get("sub"),
                is_guest=False,
                role=payload.get("role", "user"),
                permissions=payload.get("permissions", [])
            )
        except Exception as e:
            logger.warning(f"JWT verification failed: {e}")
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token"
            )

    async def _verify_guest_session(self, session_id: str) -> AuthInfo:
        """验证游客Session

        Args:
            session_id: 游客Session ID

        Returns:
            AuthInfo: 认证信息

        Raises:
            HTTPException: Session无效
        """
        try:
            # 这里简化处理，实际应该通过GuestManager验证
            # guest_manager需要数据库会话，在中间件中较难获取
            # 因此这里只做基本格式验证，详细验证在依赖函数中进行
            if not _is_valid_guest_session_id(session_id):
                raise ValueError("Invalid session format")

            return AuthInfo(
                session_id=session_id,
                is_guest=True,
                role="guest",
                permissions=["read:tools", "create:task"]
            )
        except Exception as e:
            logger.warning(f"Guest session verification failed: {e}")
            raise HTTPException(
                status_code=401,
                detail="Invalid guest session"
            )

    def _error_response(
        self,
        status_code: int,
        message: str
    ) -> JSONResponse:
        """生成错误响应"""
        return JSONResponse(
            status_code=status_code,
            content={
                "code": status_code * 100,
                "message": message,
                "data": None
            }
        )

    def _forbidden_response(self, message: str) -> JSONResponse:
        """生成禁止访问响应"""
        return JSONResponse(
            status_code=403,
            content={
                "code": 40300,
                "message": message,
                "data": None
            }
        )

    def _log_request(
        self,
        request: Request,
        response,
        auth_info: AuthInfo,
        duration: float
    ) -> None:
        """记录请求日志"""
        log_data = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "user_id": auth_info.user_id,
            "session_id": auth_info.session_id,
            "is_guest": auth_info.is_guest,
            "client_ip": self._get_client_ip(request),
            "user_agent": request.headers.get("User-Agent", "")[:100]
        }

        # 根据状态码选择日志级别
        if response.status_code >= 500:
            logger.error("Request completed with error", extra=log_data)
        elif response.status_code >= 400:
            logger.warning("Request completed with client error", extra=log_data)
        else:
            logger.info("Request completed", extra=log_data)

    def _get_client_ip(self, request: Request) -> str:
        """获取客户端IP"""
        # 检查代理头
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # 回退到直接连接IP
        if request.client:
            return request.client.host

        return "unknown"


def _is_valid_guest_session_id(session_id: str) -> bool:
    """校验游客 Session ID 是否符合当前 UUID 生成格式。"""
    try:
        return str(uuid.UUID(session_id)) == session_id
    except (TypeError, ValueError):
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """请求限流中间件

    基于IP或用户ID进行请求限流
    """

    def __init__(
        self,
        app: ASGIApp,
        cache_client=None,
        requests_per_minute: int = 60,
        burst_size: int = 10
    ):
        """初始化限流中间件

        Args:
            app: ASGI应用
            cache_client: 缓存客户端
            requests_per_minute: 每分钟允许的请求数
            burst_size: 突发请求数
        """
        super().__init__(app)
        self.cache = cache_client
        self.rpm = requests_per_minute
        self.burst = burst_size

    async def dispatch(self, request: Request, call_next):
        """限流检查"""
        # 获取限流键
        key = self._get_rate_limit_key(request)

        # 检查是否超限
        if self.cache and await self._is_rate_limited(key):
            return JSONResponse(
                status_code=429,
                content={
                    "code": 42900,
                    "message": "Too many requests, please try again later",
                    "data": None
                },
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(self.rpm),
                    "X-RateLimit-Reset": "60"
                }
            )

        # 增加计数
        if self.cache:
            await self._increment_counter(key)

        return await call_next(request)

    def _get_rate_limit_key(self, request: Request) -> str:
        """获取限流键"""
        # 优先使用用户ID
        if hasattr(request.state, "auth") and request.state.auth.user_id:
            return f"rate_limit:user:{request.state.auth.user_id}"

        # 使用IP
        client_ip = request.headers.get(
            "X-Forwarded-For",
            request.client.host if request.client else "unknown"
        )
        return f"rate_limit:ip:{client_ip}"

    async def _is_rate_limited(self, key: str) -> bool:
        """检查是否超出限流"""
        try:
            count = await self.cache.get(key)
            if count and int(count) >= self.rpm:
                return True
        except Exception as e:
            logger.warning(f"Failed to read rate limit counter: {e}")
        return False

    async def _increment_counter(self, key: str) -> None:
        """增加请求计数"""
        try:
            current = await self.cache.incr(key)
            if current == 1:
                # 第一次请求，设置过期时间
                await self.cache.expire(key, 60)
        except Exception as e:
            logger.warning(f"Failed to increment rate limit counter: {e}")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件

    记录所有请求的详细信息
    """

    # 不记录日志的路径
    SKIP_PATHS = {"/api/v1/system/health", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next):
        """记录请求日志"""
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        start_time = time.time()
        request_id = request.headers.get("X-Request-ID", str(time.time_ns()))

        # 记录请求开始
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": str(request.query_params),
                "client_ip": request.client.host if request.client else "unknown"
            }
        )

        # 执行请求
        response = await call_next(request)

        # 记录请求完成
        duration = time.time() - start_time
        logger.info(
            f"Request completed: {response.status_code} in {duration:.3f}s",
            extra={
                "request_id": request_id,
                "status_code": response.status_code,
                "duration_seconds": duration
            }
        )

        # 添加请求ID到响应头
        response.headers["X-Request-ID"] = request_id

        return response
