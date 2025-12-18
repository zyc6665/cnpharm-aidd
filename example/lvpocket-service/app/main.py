"""
FastAPI 应用入口

配置和启动 LVPocket Service
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import router
from app.api.dependencies import model_manager
from app.config import settings
from app.core.errors import (
    LVPocketError,
    lvpocket_exception_handler,
    generic_exception_handler,
)
from app.core.gpu import configure_gpu_memory_growth

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    启动时加载模型，关闭时释放资源
    """
    # 启动时
    logger.info(f"启动 {settings.APP_NAME} v{settings.APP_VERSION}")

    # 配置 GPU 内存
    configure_gpu_memory_growth()

    # 加载模型
    logger.info("正在加载模型...")
    success = model_manager.load_model()
    if success:
        logger.info("模型加载成功")
    else:
        logger.warning("模型加载失败，服务将以降级模式运行")

    yield

    # 关闭时
    logger.info("正在关闭服务...")
    model_manager.unload_model()
    logger.info("服务已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    description="""
LVPocket Service - 蛋白质结合口袋预测服务

基于 LV_NET 深度学习模型（3D CNN + Transformer）的蛋白质配体结合位点预测 API。

## 功能特性

- **口袋预测**: 预测蛋白质表面的潜在配体结合口袋
- **批量处理**: 支持多个蛋白质文件的批量预测
- **多格式输出**: 支持 JSON、MOL2、CMAP、CUBE 等格式
- **GPU 加速**: 支持 NVIDIA GPU 加速推理

## API 端点

- `GET /health` - 健康检查
- `GET /model/info` - 模型信息
- `GET /formats` - 支持的格式
- `POST /predict` - 单个预测
- `POST /batch` - 批量预测
- `POST /convert` - 格式转换
    """,
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册异常处理器
app.add_exception_handler(LVPocketError, lvpocket_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# 注册路由
app.include_router(router, tags=["LVPocket API"])


# 根路径重定向到文档
@app.get("/", include_in_schema=False)
async def root():
    """重定向到 API 文档"""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录请求日志"""
    import time

    start_time = time.time()

    # 获取请求信息
    method = request.method
    path = request.url.path
    task_id = request.headers.get("X-Task-ID", "-")

    # 处理请求
    response = await call_next(request)

    # 计算处理时间
    process_time = time.time() - start_time

    # 记录日志
    logger.info(
        f"{method} {path} | task_id={task_id} | "
        f"status={response.status_code} | time={process_time:.3f}s"
    )

    # 添加响应头
    response.headers["X-Process-Time"] = str(process_time)

    return response


def create_app() -> FastAPI:
    """工厂函数，用于创建应用实例"""
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
