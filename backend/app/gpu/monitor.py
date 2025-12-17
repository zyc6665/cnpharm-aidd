# backend/app/gpu/monitor.py
"""GPU监控模块

根据详细设计说明书 5.3 节实现。
负责GPU资源的定期监控和健康检查。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import logging
import json

from app.gpu.detector import GPUDetector, GPUStats, get_gpu_detector

logger = logging.getLogger(__name__)


@dataclass
class GPUAlert:
    """GPU告警"""
    gpu_index: int
    alert_type: str  # temperature, memory, utilization, error
    severity: str    # warning, critical
    message: str
    value: Any
    threshold: Any
    timestamp: datetime


@dataclass
class GPUMetrics:
    """GPU指标集合"""
    timestamp: datetime
    node_hostname: str
    gpu_count: int
    stats: List[GPUStats]
    alerts: List[GPUAlert]


class GPUMonitor:
    """GPU监控器

    功能：
    1. 定期采集GPU统计数据
    2. 检查GPU节点健康状态
    3. 生成告警
    4. 记录历史数据
    """

    # 默认阈值
    TEMPERATURE_WARNING = 75     # 警告温度
    TEMPERATURE_CRITICAL = 85    # 危险温度
    MEMORY_WARNING = 90          # 内存使用率警告 (%)
    MEMORY_CRITICAL = 95         # 内存使用率危险 (%)
    UTILIZATION_IDLE = 5         # 空闲判断阈值 (%)

    # 采集间隔
    DEFAULT_INTERVAL_SECONDS = 30

    def __init__(
        self,
        detector: Optional[GPUDetector] = None,
        cache_client=None,
        alert_callback=None
    ):
        """初始化GPU监控器

        Args:
            detector: GPU检测器
            cache_client: 缓存客户端（用于存储历史数据）
            alert_callback: 告警回调函数
        """
        self.detector = detector or get_gpu_detector()
        self.cache = cache_client
        self.alert_callback = alert_callback

    async def collect_gpu_stats(self) -> GPUMetrics:
        """采集GPU统计数据（定时任务）

        Returns:
            GPUMetrics: GPU指标数据
        """
        timestamp = datetime.utcnow()
        alerts = []

        if not self.detector.is_available():
            logger.warning("GPU detector not available")
            return GPUMetrics(
                timestamp=timestamp,
                node_hostname="unknown",
                gpu_count=0,
                stats=[],
                alerts=[]
            )

        node_info = self.detector.get_node_info()
        stats = self.detector.get_all_gpu_stats()

        # 检查告警条件
        for stat in stats:
            gpu_alerts = self._check_alerts(stat)
            alerts.extend(gpu_alerts)

        metrics = GPUMetrics(
            timestamp=timestamp,
            node_hostname=node_info.hostname,
            gpu_count=node_info.gpu_count,
            stats=stats,
            alerts=alerts
        )

        # 存储历史数据
        await self._store_metrics(metrics)

        # 处理告警
        for alert in alerts:
            await self._handle_alert(alert)

        logger.debug(
            f"Collected GPU stats: {node_info.gpu_count} GPUs, {len(alerts)} alerts"
        )

        return metrics

    def _check_alerts(self, stat: GPUStats) -> List[GPUAlert]:
        """检查GPU告警条件

        Args:
            stat: GPU统计数据

        Returns:
            List[GPUAlert]: 告警列表
        """
        alerts = []
        now = datetime.utcnow()

        # 温度检查
        if stat.temperature_celsius >= self.TEMPERATURE_CRITICAL:
            alerts.append(GPUAlert(
                gpu_index=stat.gpu_index,
                alert_type="temperature",
                severity="critical",
                message=f"GPU {stat.gpu_index} temperature critical: {stat.temperature_celsius}C",
                value=stat.temperature_celsius,
                threshold=self.TEMPERATURE_CRITICAL,
                timestamp=now
            ))
        elif stat.temperature_celsius >= self.TEMPERATURE_WARNING:
            alerts.append(GPUAlert(
                gpu_index=stat.gpu_index,
                alert_type="temperature",
                severity="warning",
                message=f"GPU {stat.gpu_index} temperature warning: {stat.temperature_celsius}C",
                value=stat.temperature_celsius,
                threshold=self.TEMPERATURE_WARNING,
                timestamp=now
            ))

        # 内存检查
        memory_percent = (
            stat.memory_used_mb / stat.memory_total_mb * 100
            if stat.memory_total_mb > 0 else 0
        )

        if memory_percent >= self.MEMORY_CRITICAL:
            alerts.append(GPUAlert(
                gpu_index=stat.gpu_index,
                alert_type="memory",
                severity="critical",
                message=f"GPU {stat.gpu_index} memory critical: {memory_percent:.1f}%",
                value=memory_percent,
                threshold=self.MEMORY_CRITICAL,
                timestamp=now
            ))
        elif memory_percent >= self.MEMORY_WARNING:
            alerts.append(GPUAlert(
                gpu_index=stat.gpu_index,
                alert_type="memory",
                severity="warning",
                message=f"GPU {stat.gpu_index} memory warning: {memory_percent:.1f}%",
                value=memory_percent,
                threshold=self.MEMORY_WARNING,
                timestamp=now
            ))

        return alerts

    async def _handle_alert(self, alert: GPUAlert) -> None:
        """处理告警

        Args:
            alert: 告警信息
        """
        # 记录日志
        if alert.severity == "critical":
            logger.error(alert.message, extra={
                "alert_type": alert.alert_type,
                "gpu_index": alert.gpu_index,
                "value": alert.value,
                "threshold": alert.threshold
            })
        else:
            logger.warning(alert.message, extra={
                "alert_type": alert.alert_type,
                "gpu_index": alert.gpu_index,
                "value": alert.value,
                "threshold": alert.threshold
            })

        # 调用回调
        if self.alert_callback:
            try:
                await self.alert_callback(alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

    async def _store_metrics(self, metrics: GPUMetrics) -> None:
        """存储指标到缓存

        Args:
            metrics: GPU指标
        """
        if not self.cache:
            return

        try:
            # 存储最新数据
            latest_key = "gpu:metrics:latest"
            latest_data = {
                "timestamp": metrics.timestamp.isoformat(),
                "node_hostname": metrics.node_hostname,
                "gpu_count": metrics.gpu_count,
                "stats": [
                    {
                        "gpu_index": s.gpu_index,
                        "utilization_percent": s.utilization_percent,
                        "memory_used_mb": s.memory_used_mb,
                        "memory_free_mb": s.memory_free_mb,
                        "memory_total_mb": s.memory_total_mb,
                        "temperature_celsius": s.temperature_celsius,
                        "power_watts": s.power_watts
                    }
                    for s in metrics.stats
                ]
            }
            await self.cache.set(latest_key, json.dumps(latest_data), ex=300)

            # 存储历史数据（保留24小时）
            history_key = "gpu:metrics:history"
            await self.cache.lpush(history_key, json.dumps(latest_data))
            await self.cache.ltrim(history_key, 0, 2880)  # 30秒间隔，24小时

        except Exception as e:
            logger.warning(f"Failed to store GPU metrics: {e}")

    async def check_gpu_node_health(self) -> Dict[str, Any]:
        """检查GPU节点健康状态

        Returns:
            Dict[str, Any]: 健康检查结果
        """
        health = {
            "healthy": True,
            "timestamp": datetime.utcnow().isoformat(),
            "gpu_available": self.detector.is_available(),
            "gpu_count": 0,
            "issues": [],
            "gpus": []
        }

        if not health["gpu_available"]:
            health["healthy"] = False
            health["issues"].append("GPU detection not available")
            return health

        try:
            node_info = self.detector.get_node_info()
            health["gpu_count"] = node_info.gpu_count
            health["hostname"] = node_info.hostname
            health["cuda_version"] = node_info.cuda_version
            health["driver_version"] = node_info.driver_version

            for gpu in node_info.gpus:
                gpu_health = self.detector.check_gpu_health(gpu.gpu_index)
                health["gpus"].append(gpu_health)

                if not gpu_health["healthy"]:
                    health["healthy"] = False

                health["issues"].extend(gpu_health["issues"])

        except Exception as e:
            health["healthy"] = False
            health["issues"].append(f"Health check failed: {e}")

        return health

    async def get_gpu_summary(self) -> Dict[str, Any]:
        """获取GPU摘要信息

        Returns:
            Dict[str, Any]: GPU摘要
        """
        if not self.detector.is_available():
            return {
                "available": False,
                "message": "GPU not available"
            }

        try:
            node_info = self.detector.get_node_info()
            stats = self.detector.get_all_gpu_stats()

            total_memory = sum(s.memory_total_mb for s in stats)
            used_memory = sum(s.memory_used_mb for s in stats)
            avg_utilization = (
                sum(s.utilization_percent for s in stats) / len(stats)
                if stats else 0
            )
            avg_temperature = (
                sum(s.temperature_celsius for s in stats) / len(stats)
                if stats else 0
            )

            return {
                "available": True,
                "hostname": node_info.hostname,
                "gpu_count": node_info.gpu_count,
                "cuda_version": node_info.cuda_version,
                "driver_version": node_info.driver_version,
                "total_memory_mb": total_memory,
                "used_memory_mb": used_memory,
                "free_memory_mb": total_memory - used_memory,
                "memory_usage_percent": (
                    used_memory / total_memory * 100 if total_memory > 0 else 0
                ),
                "avg_utilization_percent": avg_utilization,
                "avg_temperature_celsius": avg_temperature,
                "gpus": [
                    {
                        "index": s.gpu_index,
                        "utilization": s.utilization_percent,
                        "memory_used_mb": s.memory_used_mb,
                        "memory_total_mb": s.memory_total_mb,
                        "temperature": s.temperature_celsius,
                        "power_watts": s.power_watts
                    }
                    for s in stats
                ]
            }

        except Exception as e:
            logger.error(f"Failed to get GPU summary: {e}")
            return {
                "available": False,
                "message": str(e)
            }

    async def get_historical_metrics(
        self,
        hours: int = 1,
        interval_minutes: int = 5
    ) -> List[Dict[str, Any]]:
        """获取历史指标

        Args:
            hours: 查询小时数
            interval_minutes: 聚合间隔

        Returns:
            List[Dict[str, Any]]: 历史指标列表
        """
        if not self.cache:
            return []

        try:
            history_key = "gpu:metrics:history"
            # 计算需要获取的数据量
            data_points = hours * 60 // (self.DEFAULT_INTERVAL_SECONDS // 60) * 2

            raw_data = await self.cache.lrange(history_key, 0, data_points)

            if not raw_data:
                return []

            # 解析和聚合数据
            metrics = []
            for item in raw_data:
                try:
                    data = json.loads(item)
                    metrics.append(data)
                except json.JSONDecodeError:
                    continue

            return metrics[:data_points]

        except Exception as e:
            logger.warning(f"Failed to get historical metrics: {e}")
            return []


# Celery任务（如果使用Celery）
def create_gpu_monitoring_task(celery_app):
    """创建GPU监控Celery任务

    Args:
        celery_app: Celery应用实例

    Returns:
        Celery任务函数
    """

    @celery_app.task(name="collect_gpu_stats")
    def collect_gpu_stats_task():
        """GPU统计采集任务"""
        import asyncio
        monitor = GPUMonitor()
        asyncio.run(monitor.collect_gpu_stats())

    return collect_gpu_stats_task
