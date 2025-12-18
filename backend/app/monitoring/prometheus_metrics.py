# backend/app/monitoring/prometheus_metrics.py
"""Prometheus指标导出模块

根据详细设计说明书 7.2 节实现。
负责收集和导出Prometheus格式的监控指标。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
import time
import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# 尝试导入prometheus_client
try:
    from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False
    logger.warning("prometheus_client not available, metrics will be disabled")


@dataclass
class MetricDefinition:
    """指标定义"""
    name: str
    description: str
    labels: List[str] = field(default_factory=list)


class PrometheusMetrics:
    """Prometheus指标收集器

    定义的指标：
    - http_requests_total: HTTP请求计数器
    - http_request_duration_seconds: HTTP请求延迟直方图
    - task_execution_duration_seconds: 任务执行时间直方图
    - tasks_total: 任务计数器（按状态）
    - active_tasks: 活跃任务数量仪表盘
    - gpu_utilization: GPU利用率
    - gpu_memory_used_bytes: GPU内存使用
    - file_storage_used_bytes: 文件存储使用量
    """

    def __init__(self, namespace: str = "sciminer"):
        """初始化指标收集器

        Args:
            namespace: 指标命名空间
        """
        self.namespace = namespace
        self.enabled = HAS_PROMETHEUS

        if not self.enabled:
            logger.warning("Prometheus metrics disabled (prometheus_client not installed)")
            return

        # HTTP请求指标
        self.http_requests_total = Counter(
            f"{namespace}_http_requests_total",
            "Total number of HTTP requests",
            ["method", "endpoint", "status"]
        )

        self.http_request_duration_seconds = Histogram(
            f"{namespace}_http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        )

        # 任务指标
        self.task_execution_duration_seconds = Histogram(
            f"{namespace}_task_execution_duration_seconds",
            "Task execution duration in seconds",
            ["tool_slug", "execution_type"],
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0, 1800.0, 3600.0]
        )

        self.tasks_total = Counter(
            f"{namespace}_tasks_total",
            "Total number of tasks",
            ["status", "tool_slug"]
        )

        self.active_tasks = Gauge(
            f"{namespace}_active_tasks",
            "Number of currently active tasks",
            ["queue"]
        )

        # GPU指标
        self.gpu_utilization = Gauge(
            f"{namespace}_gpu_utilization_percent",
            "GPU utilization percentage",
            ["gpu_index", "gpu_name"]
        )

        self.gpu_memory_used_bytes = Gauge(
            f"{namespace}_gpu_memory_used_bytes",
            "GPU memory used in bytes",
            ["gpu_index", "gpu_name"]
        )

        self.gpu_memory_total_bytes = Gauge(
            f"{namespace}_gpu_memory_total_bytes",
            "GPU total memory in bytes",
            ["gpu_index", "gpu_name"]
        )

        self.gpu_temperature_celsius = Gauge(
            f"{namespace}_gpu_temperature_celsius",
            "GPU temperature in Celsius",
            ["gpu_index", "gpu_name"]
        )

        # 文件存储指标
        self.file_storage_used_bytes = Gauge(
            f"{namespace}_file_storage_used_bytes",
            "File storage used in bytes",
            ["storage_backend"]
        )

        self.file_count = Gauge(
            f"{namespace}_file_count",
            "Total number of files",
            ["source_type"]
        )

        # 用户指标
        self.active_users = Gauge(
            f"{namespace}_active_users",
            "Number of active users",
            ["user_type"]  # registered, guest
        )

        # 系统信息
        self.app_info = Info(
            f"{namespace}_app",
            "Application information"
        )

    def set_app_info(self, version: str, environment: str) -> None:
        """设置应用信息

        Args:
            version: 应用版本
            environment: 运行环境
        """
        if not self.enabled:
            return

        self.app_info.info({
            "version": version,
            "environment": environment
        })

    def record_http_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float
    ) -> None:
        """记录HTTP请求指标

        Args:
            method: HTTP方法
            endpoint: 端点路径
            status_code: 状态码
            duration: 请求时长（秒）
        """
        if not self.enabled:
            return

        self.http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=str(status_code)
        ).inc()

        self.http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)

    def record_task_execution(
        self,
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
        if not self.enabled:
            return

        self.task_execution_duration_seconds.labels(
            tool_slug=tool_slug,
            execution_type=execution_type
        ).observe(duration)

        self.tasks_total.labels(
            status=status,
            tool_slug=tool_slug
        ).inc()

    def set_active_tasks(self, queue: str, count: int) -> None:
        """设置活跃任务数

        Args:
            queue: 队列名称
            count: 任务数
        """
        if not self.enabled:
            return

        self.active_tasks.labels(queue=queue).set(count)

    def update_gpu_metrics(
        self,
        gpu_index: int,
        gpu_name: str,
        utilization: float,
        memory_used: int,
        memory_total: int,
        temperature: int
    ) -> None:
        """更新GPU指标

        Args:
            gpu_index: GPU索引
            gpu_name: GPU名称
            utilization: 利用率（百分比）
            memory_used: 已用内存（字节）
            memory_total: 总内存（字节）
            temperature: 温度（摄氏度）
        """
        if not self.enabled:
            return

        labels = {"gpu_index": str(gpu_index), "gpu_name": gpu_name}

        self.gpu_utilization.labels(**labels).set(utilization)
        self.gpu_memory_used_bytes.labels(**labels).set(memory_used)
        self.gpu_memory_total_bytes.labels(**labels).set(memory_total)
        self.gpu_temperature_celsius.labels(**labels).set(temperature)

    def set_file_storage_metrics(
        self,
        storage_backend: str,
        used_bytes: int,
        file_counts: Dict[str, int]
    ) -> None:
        """设置文件存储指标

        Args:
            storage_backend: 存储后端
            used_bytes: 使用量（字节）
            file_counts: 各类型文件数量
        """
        if not self.enabled:
            return

        self.file_storage_used_bytes.labels(
            storage_backend=storage_backend
        ).set(used_bytes)

        for source_type, count in file_counts.items():
            self.file_count.labels(source_type=source_type).set(count)

    def set_active_users(self, registered: int, guest: int) -> None:
        """设置活跃用户数

        Args:
            registered: 注册用户数
            guest: 游客数
        """
        if not self.enabled:
            return

        self.active_users.labels(user_type="registered").set(registered)
        self.active_users.labels(user_type="guest").set(guest)

    def generate_metrics(self) -> bytes:
        """生成Prometheus格式的指标数据

        Returns:
            bytes: 指标数据
        """
        if not self.enabled:
            return b"# Prometheus metrics disabled\n"

        return generate_latest()

    def get_content_type(self) -> str:
        """获取指标响应的Content-Type

        Returns:
            str: Content-Type
        """
        if not self.enabled:
            return "text/plain"

        return CONTENT_TYPE_LATEST


# 全局指标实例
_metrics: Optional[PrometheusMetrics] = None


def get_metrics() -> PrometheusMetrics:
    """获取指标收集器单例"""
    global _metrics
    if _metrics is None:
        _metrics = PrometheusMetrics()
    return _metrics


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Prometheus指标中间件

    自动记录HTTP请求指标
    """

    # 不记录指标的路径
    SKIP_PATHS = {
        "/metrics",
        "/health",
        "/ready",
        "/live",
        "/favicon.ico"
    }

    def __init__(self, app: ASGIApp, metrics: Optional[PrometheusMetrics] = None):
        """初始化中间件

        Args:
            app: ASGI应用
            metrics: 指标收集器
        """
        super().__init__(app)
        self.metrics = metrics or get_metrics()

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求并记录指标"""
        path = request.url.path

        # 跳过不需要记录的路径
        if path in self.SKIP_PATHS:
            return await call_next(request)

        # 规范化端点路径（去除动态部分）
        endpoint = self._normalize_endpoint(path)

        start_time = time.time()

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            self.metrics.record_http_request(
                method=request.method,
                endpoint=endpoint,
                status_code=response.status_code,
                duration=duration
            )

            return response

        except Exception as e:
            duration = time.time() - start_time

            self.metrics.record_http_request(
                method=request.method,
                endpoint=endpoint,
                status_code=500,
                duration=duration
            )

            raise

    def _normalize_endpoint(self, path: str) -> str:
        """规范化端点路径

        将动态路径参数替换为占位符，减少指标基数。

        Args:
            path: 原始路径

        Returns:
            str: 规范化路径
        """
        parts = path.split("/")
        normalized = []

        for part in parts:
            # 检测UUID格式
            if len(part) == 36 and part.count("-") == 4:
                normalized.append("{id}")
            # 检测纯数字
            elif part.isdigit():
                normalized.append("{id}")
            else:
                normalized.append(part)

        return "/".join(normalized)


def prometheus_middleware(app: ASGIApp) -> PrometheusMiddleware:
    """创建Prometheus中间件

    Args:
        app: ASGI应用

    Returns:
        PrometheusMiddleware: 中间件实例
    """
    return PrometheusMiddleware(app)


async def metrics_endpoint(request: Request) -> Response:
    """Prometheus指标端点

    Args:
        request: 请求对象

    Returns:
        Response: 指标响应
    """
    metrics = get_metrics()
    return Response(
        content=metrics.generate_metrics(),
        media_type=metrics.get_content_type()
    )
