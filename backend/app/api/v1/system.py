# backend/app/api/v1/system.py
"""系统管理接口"""

import os
import platform
import psutil
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.common.time import utcnow
from app.database.session import get_db
from app.config import settings, use_async_tasks
from app.auth.dependencies import get_admin_user
from app.common.responses import success_response
from app.models.users import User
from app.models.tool_packages import ToolPackage, ToolPackageVersion
from app.schemas.system_settings import ModelServiceCreate, ModelServiceUpdate
from app.services.model_services import (
    create_model_service,
    delete_model_service,
    list_model_services,
    set_default_model_service,
    test_model_service,
    update_model_service,
)

router = APIRouter()
PROJECT_ROOT = Path(__file__).resolve().parents[4]


# ==================== Schemas ====================


class ServiceStatus(BaseModel):
    """服务状态"""

    name: str
    status: str  # healthy, unhealthy, unknown
    latency_ms: Optional[float] = None
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str  # healthy, degraded, unhealthy
    version: str
    environment: str
    timestamp: str
    services: List[ServiceStatus]


class SystemInfoResponse(BaseModel):
    """系统信息响应"""

    # 应用信息
    app_name: str
    app_version: str
    environment: str
    debug: bool

    # 运行时信息
    python_version: str
    platform: str
    hostname: str

    # 配置信息
    database_type: str
    storage_backend: str
    cache_backend: str
    task_queue: str

    # 系统资源
    cpu_count: int
    memory_total_gb: float
    memory_available_gb: float
    memory_percent: float
    disk_total_gb: float
    disk_free_gb: float
    disk_percent: float


class SystemStatsResponse(BaseModel):
    """系统统计响应"""

    # 数据库统计
    total_users: int
    total_tools: int
    total_tasks: int
    total_files: int

    # 任务统计
    pending_tasks: int
    running_tasks: int
    completed_tasks: int
    failed_tasks: int

    # WebSocket 统计
    active_connections: int


# ==================== 健康检查 ====================


@router.get("/health", response_model=HealthResponse, summary="系统健康检查")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    检查系统各组件的健康状态

    返回：
    - status: healthy（所有服务正常）、degraded（部分服务异常）、unhealthy（核心服务异常）
    - services: 各服务的详细状态
    """
    services = []
    overall_status = "healthy"

    # 1. 检查数据库
    db_status = await _check_database(db)
    services.append(db_status)
    if db_status.status != "healthy":
        overall_status = "unhealthy"

    schema_status = await _check_database_schema(db)
    services.append(schema_status)
    if schema_status.status != "healthy":
        overall_status = "unhealthy"

    # 2. 检查缓存
    cache_status = await _check_cache()
    services.append(cache_status)
    if cache_status.status != "healthy" and overall_status == "healthy":
        overall_status = "degraded"

    # 3. 检查存储
    storage_status = await _check_storage()
    services.append(storage_status)
    if storage_status.status != "healthy" and overall_status == "healthy":
        overall_status = "degraded"

    # 4. 检查 Tool Package 运行时可用性
    tool_package_status = await _check_tool_package_runtime(db)
    services.append(tool_package_status)
    if tool_package_status.status != "healthy" and overall_status == "healthy":
        overall_status = "degraded"

    # 5. 检查任务队列（如果启用）
    if use_async_tasks():
        celery_status = await _check_celery()
        services.append(celery_status)
        if celery_status.status != "healthy" and overall_status == "healthy":
            overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=utcnow().isoformat(),
        services=services,
    )


async def _check_database(db: AsyncSession) -> ServiceStatus:
    """检查数据库连接"""
    start = utcnow()
    try:
        await db.execute(text("SELECT 1"))
        latency = (utcnow() - start).total_seconds() * 1000
        return ServiceStatus(
            name="database",
            status="healthy",
            latency_ms=round(latency, 2),
            message="数据库连接正常",
        )
    except Exception as e:
        return ServiceStatus(
            name="database", status="unhealthy", message=f"数据库连接失败: {str(e)}"
        )


async def _check_database_schema(db: AsyncSession) -> ServiceStatus:
    """检查数据库 Alembic 版本是否与代码迁移头一致。"""
    try:
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        script = ScriptDirectory.from_config(config)
        expected_heads = set(script.get_heads())
        if not expected_heads:
            return ServiceStatus(
                name="database_schema",
                status="unhealthy",
                message="Alembic 未找到迁移 head",
            )

        result = await db.execute(text("SELECT version_num FROM alembic_version"))
        current_revisions = {str(row[0]) for row in result.all() if row[0]}
        if current_revisions == expected_heads:
            return ServiceStatus(
                name="database_schema",
                status="healthy",
                message=f"Alembic schema 已是最新版本 ({', '.join(sorted(current_revisions))})",
            )

        current = ", ".join(sorted(current_revisions)) or "missing"
        expected = ", ".join(sorted(expected_heads))
        return ServiceStatus(
            name="database_schema",
            status="unhealthy",
            message=f"Alembic schema 版本不一致: current={current}, head={expected}",
        )
    except Exception as e:
        return ServiceStatus(
            name="database_schema",
            status="unhealthy",
            message=f"Alembic schema 检查失败: {str(e)}",
        )


async def _check_cache() -> ServiceStatus:
    """检查缓存服务"""
    start = utcnow()
    try:
        from app.cache import get_cache_backend

        cache = get_cache_backend()

        # 测试写入和读取
        test_key = "_health_check_"
        test_value = "ok"
        await cache.set(test_key, test_value, expire=10)
        result = await cache.get(test_key)
        await cache.delete(test_key)

        latency = (utcnow() - start).total_seconds() * 1000

        if result == test_value:
            return ServiceStatus(
                name="cache",
                status="healthy",
                latency_ms=round(latency, 2),
                message=f"缓存服务正常 ({settings.CACHE_BACKEND})",
            )
        else:
            return ServiceStatus(
                name="cache", status="unhealthy", message="缓存读写不一致"
            )
    except Exception as e:
        return ServiceStatus(
            name="cache", status="unhealthy", message=f"缓存服务异常: {str(e)}"
        )


async def _check_storage() -> ServiceStatus:
    """检查存储服务"""
    try:
        from app.storage import get_storage_backend

        storage = get_storage_backend()

        # 检查存储是否可用
        if settings.STORAGE_BACKEND == "local":
            # 本地存储检查目录是否可写
            storage_path = settings.STORAGE_PATH
            if os.path.exists(storage_path) and os.access(storage_path, os.W_OK):
                return ServiceStatus(
                    name="storage",
                    status="healthy",
                    message=f"本地存储正常 ({storage_path})",
                )
            else:
                return ServiceStatus(
                    name="storage",
                    status="unhealthy",
                    message=f"本地存储目录不可写: {storage_path}",
                )
        else:
            # MinIO 检查
            return ServiceStatus(
                name="storage",
                status="healthy",
                message=f"存储服务正常 ({settings.STORAGE_BACKEND})",
            )
    except Exception as e:
        return ServiceStatus(
            name="storage", status="unhealthy", message=f"存储服务异常: {str(e)}"
        )


async def _check_celery() -> ServiceStatus:
    """检查 Celery 任务队列"""
    try:
        from app.worker.celery_app import celery_app

        # 简单检查 Celery 是否配置
        if celery_app.conf.broker_url:
            return ServiceStatus(
                name="celery", status="healthy", message="Celery 已配置"
            )
        else:
            return ServiceStatus(
                name="celery", status="unknown", message="Celery 未配置"
            )
    except Exception as e:
        return ServiceStatus(
            name="celery", status="unhealthy", message=f"Celery 检查失败: {str(e)}"
        )


async def _check_tool_package_runtime(db: AsyncSession) -> ServiceStatus:
    """检查 Tool Package 新模型部署路径是否可读且发布版本可执行。"""
    try:
        if not settings.is_aidd_feature_enabled("TOOL_PACKAGE_V1_ENABLED"):
            return ServiceStatus(
                name="tool_package_runtime",
                status="unknown",
                message="Tool Package 功能未启用",
            )

        total_packages = await db.scalar(select(func.count(ToolPackage.id))) or 0
        published_packages = (
            await db.scalar(
                select(func.count(ToolPackage.id)).where(ToolPackage.status == "published")
            )
            or 0
        )
        ready_packages = (
            await db.scalar(
                select(func.count(ToolPackage.id))
                .join(
                    ToolPackageVersion,
                    ToolPackage.current_version_id == ToolPackageVersion.id,
                )
                .where(
                    ToolPackage.status == "published",
                    ToolPackageVersion.validation_status == "valid",
                    ToolPackageVersion.is_signed.is_(True),
                )
            )
            or 0
        )
        blocked_packages = published_packages - ready_packages
        if blocked_packages > 0:
            return ServiceStatus(
                name="tool_package_runtime",
                status="unhealthy",
                message=(
                    "Tool Package runtime 存在未就绪发布版本: "
                    f"ready={ready_packages}, blocked={blocked_packages}, total={total_packages}"
                ),
            )
        return ServiceStatus(
            name="tool_package_runtime",
            status="healthy",
            message=(
                "Tool Package runtime 可用: "
                f"ready={ready_packages}, published={published_packages}, total={total_packages}"
            ),
        )
    except Exception as e:
        return ServiceStatus(
            name="tool_package_runtime",
            status="unknown",
            message=f"Tool Package runtime 检查不可用: {str(e)}",
        )


# ==================== 系统信息 ====================


@router.get("/info", response_model=dict, summary="获取系统信息")
async def get_system_info(admin_user: User = Depends(get_admin_user)):
    """
    获取系统详细信息（仅管理员可访问）

    包括：
    - 应用配置信息
    - 运行时环境信息
    - 系统资源使用情况
    """
    # 系统资源
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # 数据库类型
    if "sqlite" in settings.DATABASE_URL:
        db_type = "SQLite"
    elif "postgresql" in settings.DATABASE_URL:
        db_type = "PostgreSQL"
    else:
        db_type = "Unknown"

    # 任务队列
    task_queue = "Celery" if use_async_tasks() else "Sync (开发模式)"

    return success_response(
        data=SystemInfoResponse(
            app_name=settings.APP_NAME,
            app_version=settings.APP_VERSION,
            environment=settings.ENVIRONMENT,
            debug=settings.DEBUG,
            python_version=platform.python_version(),
            platform=f"{platform.system()} {platform.release()}",
            hostname=platform.node(),
            database_type=db_type,
            storage_backend=settings.STORAGE_BACKEND,
            cache_backend=settings.CACHE_BACKEND,
            task_queue=task_queue,
            cpu_count=psutil.cpu_count(),
            memory_total_gb=round(memory.total / (1024**3), 2),
            memory_available_gb=round(memory.available / (1024**3), 2),
            memory_percent=memory.percent,
            disk_total_gb=round(disk.total / (1024**3), 2),
            disk_free_gb=round(disk.free / (1024**3), 2),
            disk_percent=disk.percent,
        ).model_dump()
    )


# ==================== 系统统计 ====================


@router.get("/stats", response_model=dict, summary="获取系统统计")
async def get_system_stats(
    admin_user: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)
):
    """
    获取系统统计数据（仅管理员可访问）

    包括：
    - 数据库统计（用户数、工具数、任务数、文件数）
    - 任务状态统计
    - WebSocket 连接数
    """
    from sqlalchemy import func
    from app.models.users import User
    from app.models.tools import Tool
    from app.models.tasks import Task, TaskStatus
    from app.models.files import File
    from app.websocket import ws_manager

    # 用户数
    users_result = await db.execute(select(func.count(User.id)))
    total_users = users_result.scalar()

    # 工具数
    tools_result = await db.execute(select(func.count(Tool.id)))
    total_tools = tools_result.scalar()

    # 任务数
    tasks_result = await db.execute(select(func.count(Task.id)))
    total_tasks = tasks_result.scalar()

    # 文件数
    files_result = await db.execute(select(func.count(File.id)))
    total_files = files_result.scalar()

    # 任务状态统计
    pending_result = await db.execute(
        select(func.count(Task.id)).where(Task.status == TaskStatus.PENDING.value)
    )
    pending_tasks = pending_result.scalar()

    running_result = await db.execute(
        select(func.count(Task.id)).where(Task.status == TaskStatus.RUNNING.value)
    )
    running_tasks = running_result.scalar()

    completed_result = await db.execute(
        select(func.count(Task.id)).where(Task.status == TaskStatus.SUCCESS.value)
    )
    completed_tasks = completed_result.scalar()

    failed_result = await db.execute(
        select(func.count(Task.id)).where(Task.status == TaskStatus.FAILURE.value)
    )
    failed_tasks = failed_result.scalar()

    # WebSocket 连接数
    active_connections = ws_manager.get_connection_count()

    return success_response(
        data=SystemStatsResponse(
            total_users=total_users,
            total_tools=total_tools,
            total_tasks=total_tasks,
            total_files=total_files,
            pending_tasks=pending_tasks,
            running_tasks=running_tasks,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            active_connections=active_connections,
        ).model_dump()
    )


# ==================== 配置管理 ====================


@router.get("/model-services", response_model=dict, summary="获取模型服务配置")
async def list_model_service_settings(
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    services = await list_model_services(db)
    return success_response(
        data={
            "items": [service.model_dump() for service in services],
            "total": len(services),
        }
    )


@router.post("/model-services", response_model=dict, summary="创建模型服务配置")
async def create_model_service_setting(
    service_data: ModelServiceCreate,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = await create_model_service(db, service_data)
    return success_response(data=service.model_dump(), message="模型服务已创建")


@router.put(
    "/model-services/{service_id}", response_model=dict, summary="更新模型服务配置"
)
async def update_model_service_setting(
    service_id: str,
    service_data: ModelServiceUpdate,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = await update_model_service(db, service_id, service_data)
    return success_response(data=service.model_dump(), message="模型服务已更新")


@router.delete(
    "/model-services/{service_id}", response_model=dict, summary="删除模型服务配置"
)
async def delete_model_service_setting(
    service_id: str,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    await delete_model_service(db, service_id)
    return success_response(data={"id": service_id}, message="模型服务已删除")


@router.post(
    "/model-services/{service_id}/set-default",
    response_model=dict,
    summary="设置默认模型服务",
)
async def set_default_model_service_setting(
    service_id: str,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = await set_default_model_service(db, service_id)
    return success_response(data=service.model_dump(), message="默认模型服务已更新")


@router.post(
    "/model-services/{service_id}/test", response_model=dict, summary="测试模型服务连接"
)
async def test_model_service_setting(
    service_id: str,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await test_model_service(db, service_id)
    return success_response(data=result.model_dump(), message=result.message)


@router.get("/config", summary="获取系统配置（管理员）")
async def get_system_config(admin_user: User = Depends(get_admin_user)):
    """
    获取当前系统配置（仅管理员可访问）

    注意：敏感信息（密钥、密码等）会被隐藏
    """
    return success_response(
        data={
            "environment": settings.ENVIRONMENT,
            "debug": settings.DEBUG,
            "api_prefix": settings.API_V1_PREFIX,
            "database": {
                "type": "SQLite" if "sqlite" in settings.DATABASE_URL else "PostgreSQL",
                "pool_size": settings.DB_POOL_SIZE,
                "max_overflow": settings.DB_MAX_OVERFLOW,
            },
            "storage": {
                "backend": settings.STORAGE_BACKEND,
                "path": (
                    settings.STORAGE_PATH
                    if settings.STORAGE_BACKEND == "local"
                    else None
                ),
                "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
            },
            "cache": {"backend": settings.CACHE_BACKEND},
            "jwt": {
                "algorithm": settings.JWT_ALGORITHM,
                "access_token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
                "refresh_token_expire_days": settings.REFRESH_TOKEN_EXPIRE_DAYS,
            },
            "cors_origins": settings.CORS_ORIGINS,
            "log_level": settings.LOG_LEVEL,
        }
    )


@router.get("/feature-flags", response_model=dict, summary="获取功能开关状态（管理员）")
async def get_feature_flags(admin_user: User = Depends(get_admin_user)):
    """返回 AIDD 首月发布门禁开关，便于上线前审计。"""
    flags = settings.aidd_feature_flags()
    return success_response(
        data={
            "environment": settings.ENVIRONMENT,
            "items": flags,
            "enabled_count": sum(1 for item in flags if item["enabled"]),
            "total": len(flags),
        }
    )
