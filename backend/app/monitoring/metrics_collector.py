# backend/app/monitoring/metrics_collector.py
"""指标采集器

负责定时采集系统各项指标并更新Prometheus指标。
"""

from datetime import timedelta
from typing import Any, Dict, Optional
import asyncio
import logging

from app.common.time import utcnow
from app.monitoring.prometheus_metrics import get_metrics, PrometheusMetrics
from app.monitoring.alert_manager import get_alert_manager, AlertSeverity

logger = logging.getLogger(__name__)


class MetricsCollector:
    """指标采集器

    定时采集以下指标：
    1. GPU利用率和内存
    2. 任务队列状态
    3. 文件存储使用量
    4. 活跃用户数
    """

    # 采集间隔（秒）
    DEFAULT_INTERVAL = 30

    def __init__(
        self,
        metrics: Optional[PrometheusMetrics] = None,
        db_session_factory=None,
        cache_client=None
    ):
        """初始化指标采集器

        Args:
            metrics: Prometheus指标收集器
            db_session_factory: 数据库会话工厂
            cache_client: 缓存客户端
        """
        self.metrics = metrics or get_metrics()
        self.db_factory = db_session_factory
        self.cache = cache_client
        self._running = False

    async def collect_all(self) -> Dict[str, Any]:
        """采集所有指标

        Returns:
            Dict[str, Any]: 采集结果
        """
        results = {
            "timestamp": utcnow().isoformat(),
            "gpu": None,
            "tasks": None,
            "files": None,
            "users": None,
            "errors": []
        }

        # 并行采集
        tasks = [
            self._collect_gpu_metrics(),
            self._collect_task_metrics(),
            self._collect_file_metrics(),
            self._collect_user_metrics()
        ]

        collected = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(collected):
            if isinstance(result, Exception):
                results["errors"].append(str(result))
                logger.warning(f"Metrics collection error: {result}")
            else:
                key = ["gpu", "tasks", "files", "users"][i]
                results[key] = result

        return results

    async def _collect_gpu_metrics(self) -> Dict[str, Any]:
        """采集GPU指标"""
        try:
            from app.gpu.detector import get_gpu_detector

            detector = get_gpu_detector()
            if not detector.is_available():
                return {"available": False}

            stats = detector.get_all_gpu_stats()

            for stat in stats:
                self.metrics.update_gpu_metrics(
                    gpu_index=stat.gpu_index,
                    gpu_name=f"GPU-{stat.gpu_index}",
                    utilization=stat.utilization_percent,
                    memory_used=stat.memory_used_mb * 1024 * 1024,
                    memory_total=stat.memory_total_mb * 1024 * 1024,
                    temperature=stat.temperature_celsius
                )

                # 检查告警条件
                await self._check_gpu_alerts(stat)

            return {
                "available": True,
                "gpu_count": len(stats),
                "avg_utilization": sum(s.utilization_percent for s in stats) / len(stats) if stats else 0
            }

        except ImportError:
            return {"available": False, "error": "GPU module not available"}
        except Exception as e:
            logger.error(f"GPU metrics collection failed: {e}")
            raise

    async def _collect_task_metrics(self) -> Dict[str, Any]:
        """采集任务指标"""
        try:
            # 从Celery获取队列状态
            from app.worker.celery_app import celery_app

            inspect = celery_app.control.inspect()

            # 活跃任务
            active = inspect.active() or {}
            active_count = sum(len(tasks) for tasks in active.values())

            # 预定任务
            scheduled = inspect.scheduled() or {}
            scheduled_count = sum(len(tasks) for tasks in scheduled.values())

            # 保留任务
            reserved = inspect.reserved() or {}
            reserved_count = sum(len(tasks) for tasks in reserved.values())

            # 更新指标
            self.metrics.set_active_tasks("active", active_count)
            self.metrics.set_active_tasks("scheduled", scheduled_count)
            self.metrics.set_active_tasks("reserved", reserved_count)

            return {
                "active": active_count,
                "scheduled": scheduled_count,
                "reserved": reserved_count
            }

        except ImportError:
            return {"error": "Celery not available"}
        except Exception as e:
            logger.warning(f"Task metrics collection failed: {e}")
            return {"error": str(e)}

    async def _collect_file_metrics(self) -> Dict[str, Any]:
        """采集文件存储指标"""
        if not self.db_factory:
            return {"error": "Database not configured"}

        try:
            from sqlalchemy import select, func
            from app.models.files import File

            async with self.db_factory() as db:
                # 总文件数和大小
                result = await db.execute(
                    select(
                        func.count(File.id),
                        func.coalesce(func.sum(File.size_bytes), 0)
                    ).where(File.deleted_at == None)
                )
                total_count, total_size = result.one()

                # 按来源统计
                source_result = await db.execute(
                    select(
                        File.source_type,
                        func.count(File.id)
                    ).where(File.deleted_at == None).group_by(File.source_type)
                )
                source_counts = {row[0]: row[1] for row in source_result}

            # 更新指标
            self.metrics.set_file_storage_metrics(
                storage_backend="default",
                used_bytes=total_size or 0,
                file_counts=source_counts
            )

            return {
                "total_files": total_count or 0,
                "total_size_bytes": total_size or 0,
                "by_source": source_counts
            }

        except Exception as e:
            logger.warning(f"File metrics collection failed: {e}")
            return {"error": str(e)}

    async def _collect_user_metrics(self) -> Dict[str, Any]:
        """采集用户指标"""
        if not self.db_factory:
            return {"error": "Database not configured"}

        try:
            from sqlalchemy import select, func
            from app.models.users import User

            async with self.db_factory() as db:
                # 活跃用户（最近1小时更新过资料或账户状态）
                cutoff = utcnow() - timedelta(hours=1)

                active_result = await db.execute(
                    select(func.count(User.id)).where(User.updated_at >= cutoff)
                )
                active_users = active_result.scalar() or 0

            # 更新指标
            self.metrics.set_active_users(active_users)

            return {
                "active_users": active_users
            }

        except Exception as e:
            logger.warning(f"User metrics collection failed: {e}")
            return {"error": str(e)}

    async def _check_gpu_alerts(self, stat) -> None:
        """检查GPU告警条件"""
        alert_manager = get_alert_manager()

        # 温度告警
        if stat.temperature_celsius >= 85:
            await alert_manager.send_alert(
                title=f"GPU {stat.gpu_index} Temperature Critical",
                message=f"GPU {stat.gpu_index} temperature is {stat.temperature_celsius}C",
                severity=AlertSeverity.CRITICAL,
                source="gpu",
                labels={"gpu_index": str(stat.gpu_index)},
                dedupe_key=f"gpu:{stat.gpu_index}:temp:critical"
            )
        elif stat.temperature_celsius >= 75:
            await alert_manager.send_alert(
                title=f"GPU {stat.gpu_index} Temperature Warning",
                message=f"GPU {stat.gpu_index} temperature is {stat.temperature_celsius}C",
                severity=AlertSeverity.WARNING,
                source="gpu",
                labels={"gpu_index": str(stat.gpu_index)},
                dedupe_key=f"gpu:{stat.gpu_index}:temp:warning"
            )

        # 内存告警
        memory_percent = stat.memory_used_mb / stat.memory_total_mb * 100
        if memory_percent >= 95:
            await alert_manager.send_alert(
                title=f"GPU {stat.gpu_index} Memory Critical",
                message=f"GPU {stat.gpu_index} memory usage is {memory_percent:.1f}%",
                severity=AlertSeverity.WARNING,
                source="gpu",
                labels={"gpu_index": str(stat.gpu_index)},
                dedupe_key=f"gpu:{stat.gpu_index}:memory:critical"
            )

    async def start_collection_loop(self, interval: int = DEFAULT_INTERVAL) -> None:
        """启动采集循环

        Args:
            interval: 采集间隔（秒）
        """
        self._running = True
        logger.info(f"Starting metrics collection loop (interval={interval}s)")

        while self._running:
            try:
                await self.collect_all()
            except Exception as e:
                logger.error(f"Metrics collection loop error: {e}")

            await asyncio.sleep(interval)

    def stop(self) -> None:
        """停止采集循环"""
        self._running = False
        logger.info("Metrics collection loop stopped")


# Celery任务
def create_metrics_collection_task(celery_app):
    """创建指标采集Celery任务

    Args:
        celery_app: Celery应用实例

    Returns:
        Celery任务函数
    """

    @celery_app.task(name="collect_system_metrics")
    def collect_system_metrics():
        """系统指标采集任务"""
        import asyncio
        collector = MetricsCollector()
        return asyncio.run(collector.collect_all())

    return collect_system_metrics


async def record_task_metrics(
    tool_slug: str,
    execution_type: str,
    duration: float,
    status: str
) -> None:
    """记录任务执行指标

    Args:
        tool_slug: 工具标识
        execution_type: 执行类型
        duration: 执行时长（秒）
        status: 任务状态
    """
    metrics = get_metrics()
    metrics.record_task_execution(
        tool_slug=tool_slug,
        execution_type=execution_type,
        duration=duration,
        status=status
    )
