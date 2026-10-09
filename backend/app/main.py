# backend/app/main.py
"""FastAPI 主应用入口"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings, use_direct_task_execution
from app.cache import get_cache
from app.database.session import init_db
from app.api.v1 import api_router
from app.common.exceptions import AppException
from app.middleware import RateLimitMiddleware
from app.tasks.direct_recovery import direct_task_recovery_loop
from app.tasks.direct_runner import direct_task_runner
from app.tasks.remote_recovery import remote_task_recovery_loop
from app.agents.aidd.background import agent_reconcile_loop
from app.services.workflow_reconciliation import workflow_reconcile_loop
from app.worker.celery_app import configure_managed_execution_runtime

logger = logging.getLogger(__name__)


def configure_direct_managed_execution_runtime():
    """Register managed execution adapters for the direct task runner only."""
    if not use_direct_task_execution():
        return None
    return configure_managed_execution_runtime()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    await init_db()
    managed_runtime = configure_direct_managed_execution_runtime()
    agent_reconcile_loop.start()
    workflow_reconcile_loop.start()
    if use_direct_task_execution():
        direct_task_recovery_loop.start()
        remote_task_recovery_loop.start()
    logger.info("数据库初始化完成")
    yield
    # 关闭时清理资源
    await agent_reconcile_loop.stop()
    await workflow_reconcile_loop.stop()
    if use_direct_task_execution():
        await direct_task_recovery_loop.stop()
        await remote_task_recovery_loop.stop()
        await direct_task_runner.shutdown()
    if managed_runtime is not None:
        await managed_runtime.close()
    logger.info("应用关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    description="科学计算工具管理平台API",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# 先注册限流，再注册 CORS，确保限流响应仍带有 CORS 响应头。
app.add_middleware(
    RateLimitMiddleware,
    cache_client=get_cache(),
    requests_per_minute=settings.REQUEST_RATE_LIMIT_PER_MINUTE,
    trust_proxy_headers=settings.RATE_LIMIT_TRUST_PROXY_HEADERS,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理器
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """处理应用异常"""
    return JSONResponse(
        status_code=exc.code,
        content={
            "code": exc.code,
            "message": exc.message,
            "data": None,
            "detail": exc.detail
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """处理未知异常"""
    logger.error(
        "Unhandled API exception: %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "服务器内部错误",
            "data": None,
            "detail": str(exc) if settings.DEBUG else None
        }
    )


# 注册API路由
app.include_router(api_router, prefix="/api/v1")


# 根路径
@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "status": "running"
    }


# 健康检查
@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
