"""FastAPI 服务入口。"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.adapter import ModelAdapter
from app.config import settings
from app.errors import ToolServiceError
from app.schemas import ErrorInfo, HealthResponse, PredictRequest, PredictResponse


logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)
adapter = ModelAdapter()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时加载模型。"""
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    adapter.load_model()
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="通用 remote_api 工具服务模板",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    """健康检查。"""
    return HealthResponse(
        status="healthy",
        service=settings.app_name,
        version=settings.app_version,
    )


@app.post("/predict", response_model=PredictResponse, tags=["prediction"])
async def predict(request: PredictRequest) -> PredictResponse:
    """统一预测接口。"""
    try:
        return await adapter.predict(request)
    except ToolServiceError as exc:
        logger.warning("Business error: %s", exc.message)
        return PredictResponse(
            success=False,
            task_id=request.task_id,
            result=None,
            output_files=[],
            error=ErrorInfo(code=exc.code, message=exc.message),
        )
    except Exception as exc:  # pragma: no cover - 防御性分支
        logger.exception("Unexpected prediction error")
        return PredictResponse(
            success=False,
            task_id=request.task_id,
            result=None,
            output_files=[],
            error=ErrorInfo(code="UNEXPECTED_ERROR", message=str(exc)),
        )


@app.get("/", include_in_schema=False)
async def root() -> dict:
    """根路径。"""
    return {"service": settings.app_name, "docs": "/docs", "health": "/health"}


def create_app() -> FastAPI:
    """工厂函数。"""
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
