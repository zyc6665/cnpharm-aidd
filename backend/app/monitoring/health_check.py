# backend/app/monitoring/health_check.py
"""健康检查模块

根据详细设计说明书 7.1 节实现。
负责系统健康检查、就绪检查、存活检查。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import asyncio
import logging
import time

from app.common.time import utcnow

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # 部分服务不可用
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """组件健康状态"""
    name: str
    status: HealthStatus
    latency_ms: Optional[float] = None
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealth:
    """系统健康状态"""
    status: HealthStatus
    timestamp: str
    version: str
    uptime_seconds: float
    components: List[ComponentHealth]
    message: str = ""


class HealthChecker:
    """健康检查器

    功能：
    1. 综合健康检查（/system/health）
    2. K8s就绪检查（/system/ready）
    3. K8s存活检查（/system/live）
    4. 各组件健康检查
    """

    # 组件检查超时（秒）
    CHECK_TIMEOUT = 5.0

    # 数据库延迟阈值（毫秒）
    DB_LATENCY_WARNING = 100
    DB_LATENCY_CRITICAL = 500

    # Redis延迟阈值（毫秒）
    REDIS_LATENCY_WARNING = 50
    REDIS_LATENCY_CRITICAL = 200

    def __init__(
        self,
        db_session_factory=None,
        cache_client=None,
        version: str = "1.0.0",
        start_time: Optional[datetime] = None
    ):
        """初始化健康检查器

        Args:
            db_session_factory: 数据库会话工厂
            cache_client: 缓存客户端
            version: 应用版本
            start_time: 应用启动时间
        """
        self.db_factory = db_session_factory
        self.cache = cache_client
        self.version = version
        self.start_time = start_time or utcnow()

    async def health_check(self) -> SystemHealth:
        """综合健康检查

        Returns:
            SystemHealth: 系统健康状态
        """
        components = []
        overall_status = HealthStatus.HEALTHY

        # 并行检查各组件
        checks = [
            self._check_database(),
            self._check_redis(),
            self._check_celery(),
            self._check_storage(),
            self._check_gpu(),
        ]

        results = await asyncio.gather(*checks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                components.append(ComponentHealth(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=str(result)
                ))
                overall_status = HealthStatus.UNHEALTHY
            elif isinstance(result, ComponentHealth):
                components.append(result)
                if result.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif result.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED

        uptime = (utcnow() - self.start_time).total_seconds()

        return SystemHealth(
            status=overall_status,
            timestamp=utcnow().isoformat(),
            version=self.version,
            uptime_seconds=uptime,
            components=components,
            message=self._get_status_message(overall_status)
        )

    async def readiness_check(self) -> Dict[str, Any]:
        """K8s就绪检查

        检查应用是否准备好接收流量。

        Returns:
            Dict[str, Any]: 就绪状态
        """
        checks = {
            "database": False,
            "cache": False
        }

        # 检查数据库
        try:
            db_health = await self._check_database()
            checks["database"] = db_health.status != HealthStatus.UNHEALTHY
        except Exception:
            checks["database"] = False

        # 检查缓存
        try:
            redis_health = await self._check_redis()
            checks["cache"] = redis_health.status != HealthStatus.UNHEALTHY
        except Exception:
            checks["cache"] = False

        ready = all(checks.values())

        return {
            "ready": ready,
            "checks": checks,
            "timestamp": utcnow().isoformat()
        }

    async def liveness_check(self) -> Dict[str, Any]:
        """K8s存活检查

        检查应用是否存活。

        Returns:
            Dict[str, Any]: 存活状态
        """
        # 存活检查应该简单快速
        return {
            "alive": True,
            "timestamp": utcnow().isoformat(),
            "uptime_seconds": (utcnow() - self.start_time).total_seconds()
        }

    async def _check_database(self) -> ComponentHealth:
        """检查数据库健康状态"""
        if not self.db_factory:
            return ComponentHealth(
                name="database",
                status=HealthStatus.DEGRADED,
                message="Database not configured"
            )

        try:
            start = time.time()

            async with self.db_factory() as db:
                # 执行简单查询测试连接
                from sqlalchemy import text
                await db.execute(text("SELECT 1"))

            latency = (time.time() - start) * 1000

            # 根据延迟判断状态
            if latency > self.DB_LATENCY_CRITICAL:
                status = HealthStatus.DEGRADED
                message = f"High latency: {latency:.1f}ms"
            elif latency > self.DB_LATENCY_WARNING:
                status = HealthStatus.HEALTHY
                message = f"Warning: latency {latency:.1f}ms"
            else:
                status = HealthStatus.HEALTHY
                message = "OK"

            return ComponentHealth(
                name="database",
                status=status,
                latency_ms=latency,
                message=message
            )

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=str(e)
            )

    async def _check_redis(self) -> ComponentHealth:
        """检查Redis健康状态"""
        if not self.cache:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.DEGRADED,
                message="Redis not configured"
            )

        try:
            start = time.time()

            # PING测试
            await self.cache.ping()

            latency = (time.time() - start) * 1000

            # 根据延迟判断状态
            if latency > self.REDIS_LATENCY_CRITICAL:
                status = HealthStatus.DEGRADED
                message = f"High latency: {latency:.1f}ms"
            elif latency > self.REDIS_LATENCY_WARNING:
                status = HealthStatus.HEALTHY
                message = f"Warning: latency {latency:.1f}ms"
            else:
                status = HealthStatus.HEALTHY
                message = "OK"

            return ComponentHealth(
                name="redis",
                status=status,
                latency_ms=latency,
                message=message
            )

        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=str(e)
            )

    async def _check_celery(self) -> ComponentHealth:
        """检查Celery健康状态"""
        try:
            from app.worker.celery_app import celery_app

            # 检查Celery连接
            inspect = celery_app.control.inspect()
            stats = inspect.stats()

            if stats:
                worker_count = len(stats)
                return ComponentHealth(
                    name="celery",
                    status=HealthStatus.HEALTHY,
                    message=f"{worker_count} workers online",
                    details={"worker_count": worker_count}
                )
            else:
                return ComponentHealth(
                    name="celery",
                    status=HealthStatus.DEGRADED,
                    message="No workers available"
                )

        except ImportError:
            return ComponentHealth(
                name="celery",
                status=HealthStatus.DEGRADED,
                message="Celery not configured"
            )
        except Exception as e:
            logger.warning(f"Celery health check failed: {e}")
            return ComponentHealth(
                name="celery",
                status=HealthStatus.DEGRADED,
                message=str(e)
            )

    async def _check_storage(self) -> ComponentHealth:
        """检查存储服务健康状态"""
        try:
            from app.storage.factory import get_storage

            storage = get_storage()

            # 尝试列出文件（验证连接）
            start = time.time()
            await storage.list_files("", limit=1)
            latency = (time.time() - start) * 1000

            return ComponentHealth(
                name="storage",
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="OK"
            )

        except ImportError:
            return ComponentHealth(
                name="storage",
                status=HealthStatus.DEGRADED,
                message="Storage not configured"
            )
        except Exception as e:
            logger.warning(f"Storage health check failed: {e}")
            return ComponentHealth(
                name="storage",
                status=HealthStatus.DEGRADED,
                message=str(e)
            )

    async def _check_gpu(self) -> ComponentHealth:
        """检查GPU健康状态"""
        try:
            from app.gpu.detector import get_gpu_detector

            detector = get_gpu_detector()

            if not detector.is_available():
                return ComponentHealth(
                    name="gpu",
                    status=HealthStatus.DEGRADED,
                    message="GPU not available"
                )

            gpus = detector.detect_gpus()
            gpu_count = len(gpus)

            if gpu_count == 0:
                return ComponentHealth(
                    name="gpu",
                    status=HealthStatus.DEGRADED,
                    message="No GPU detected"
                )

            # 检查GPU健康
            unhealthy_gpus = []
            for gpu in gpus:
                health = detector.check_gpu_health(gpu.gpu_index)
                if not health["healthy"]:
                    unhealthy_gpus.append(gpu.gpu_index)

            if unhealthy_gpus:
                return ComponentHealth(
                    name="gpu",
                    status=HealthStatus.DEGRADED,
                    message=f"Unhealthy GPUs: {unhealthy_gpus}",
                    details={"gpu_count": gpu_count, "unhealthy": unhealthy_gpus}
                )

            return ComponentHealth(
                name="gpu",
                status=HealthStatus.HEALTHY,
                message=f"{gpu_count} GPUs healthy",
                details={"gpu_count": gpu_count}
            )

        except ImportError:
            return ComponentHealth(
                name="gpu",
                status=HealthStatus.DEGRADED,
                message="GPU module not available"
            )
        except Exception as e:
            logger.warning(f"GPU health check failed: {e}")
            return ComponentHealth(
                name="gpu",
                status=HealthStatus.DEGRADED,
                message=str(e)
            )

    def _get_status_message(self, status: HealthStatus) -> str:
        """获取状态消息"""
        messages = {
            HealthStatus.HEALTHY: "All systems operational",
            HealthStatus.DEGRADED: "Some services degraded",
            HealthStatus.UNHEALTHY: "System unhealthy"
        }
        return messages.get(status, "Unknown status")

    def to_dict(self, health: SystemHealth) -> Dict[str, Any]:
        """转换为字典格式

        Args:
            health: 系统健康状态

        Returns:
            Dict[str, Any]: 字典格式
        """
        return {
            "status": health.status.value,
            "timestamp": health.timestamp,
            "version": health.version,
            "uptime_seconds": health.uptime_seconds,
            "message": health.message,
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "latency_ms": c.latency_ms,
                    "message": c.message,
                    "details": c.details
                }
                for c in health.components
            ]
        }
