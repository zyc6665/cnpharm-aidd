# backend/app/worker/celery_app.py
"""Celery 应用配置"""

from celery import Celery
from app.config import settings


def create_celery_app() -> Celery:
    """
    创建 Celery 应用

    支持两种模式：
    1. 开发模式：使用内存队列（同步执行）
    2. 生产模式：使用 Redis 作为消息代理
    """
    # 根据环境选择消息代理
    if settings.CELERY_BROKER_URL:
        broker_url = settings.CELERY_BROKER_URL
        result_backend = settings.CELERY_RESULT_BACKEND or settings.CELERY_BROKER_URL
    else:
        # 开发模式：使用内存
        broker_url = "memory://"
        result_backend = "cache+memory://"

    app = Celery(
        "scitool_worker",
        broker=broker_url,
        backend=result_backend,
        include=[
            "app.worker.tasks",
        ]
    )

    heartbeat_queues = [
        queue.strip()
        for queue in (settings.WORKER_CAPABILITY_HEARTBEAT_QUEUES or "default").split(",")
        if queue.strip()
    ]
    heartbeat_schedule = {
        f"heartbeat-worker-capability-{queue}": {
            "task": "app.worker.tasks.heartbeat_worker_capability",
            "schedule": 30.0,
            "options": {"queue": queue},
        }
        for queue in heartbeat_queues
    }

    # Celery 配置
    app.conf.update(
        # 任务序列化
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",

        # 时区
        timezone="Asia/Shanghai",
        enable_utc=True,

        # 任务路由
        task_routes={
            "app.worker.tasks.execute_tool_task": {"queue": "tool_tasks"},
            "app.worker.tasks.cleanup_expired_files": {"queue": "maintenance"},
            "app.worker.tasks.reclaim_stale_gpu_leases": {"queue": "maintenance"},
            "app.worker.tasks.reclaim_stale_resource_reservations": {"queue": "maintenance"},
            "app.worker.tasks.reclaim_stale_cancellations": {"queue": "maintenance"},
            "app.worker.tasks.reconcile_execution_records": {"queue": "maintenance"},
            "app.worker.tasks.reconcile_remote_tasks": {"queue": "maintenance"},
            "app.worker.tasks.reconcile_remote_cancellations": {"queue": "maintenance"},
            "app.worker.tasks.collect_gpu_stats": {"queue": "monitoring"},
        },

        # 默认队列
        task_default_queue="default",

        # 任务结果过期时间（1天）
        result_expires=86400,

        # 任务超时
        task_soft_time_limit=3600,  # 1小时软超时
        task_time_limit=3660,  # 1小时1分钟硬超时

        # 并发控制
        worker_prefetch_multiplier=1,
        worker_concurrency=4,

        # 任务重试
        task_acks_late=True,
        task_reject_on_worker_lost=True,

        # 定时任务
        beat_schedule={
            # 每小时清理过期文件
            "cleanup-expired-files": {
                "task": "app.worker.tasks.cleanup_expired_files",
                "schedule": 3600.0,
            },
            "reclaim-stale-gpu-leases": {
                "task": "app.worker.tasks.reclaim_stale_gpu_leases",
                "schedule": 60.0,
            },
            "reclaim-stale-resource-reservations": {
                "task": "app.worker.tasks.reclaim_stale_resource_reservations",
                "schedule": 60.0,
            },
            "reclaim-stale-cancellations": {
                "task": "app.worker.tasks.reclaim_stale_cancellations",
                "schedule": 60.0,
            },
            **heartbeat_schedule,
            "reconcile-execution-records": {
                "task": "app.worker.tasks.reconcile_execution_records",
                "schedule": float(settings.EXECUTION_RECORD_RECONCILE_INTERVAL_SECONDS),
            },
            "reconcile-remote-tasks": {
                "task": "app.worker.tasks.reconcile_remote_tasks",
                "schedule": float(settings.REMOTE_TASK_RECOVERY_INTERVAL_SECONDS),
            },
            "reconcile-remote-cancellations": {
                "task": "app.worker.tasks.reconcile_remote_cancellations",
                "schedule": float(settings.REMOTE_CANCEL_RETRY_INTERVAL_SECONDS),
            },
            # 每分钟收集 GPU 统计
            "collect-gpu-stats": {
                "task": "app.worker.tasks.collect_gpu_stats",
                "schedule": 60.0,
            },
        },
    )

    return app


# 创建 Celery 实例
celery_app = create_celery_app()


# 开发模式同步执行支持
class SyncTaskExecutor:
    """
    同步任务执行器

    开发环境下不启动 Celery Worker 时使用
    """

    @staticmethod
    async def execute_tool_task(task_id: str, params: dict):
        """同步执行工具任务"""
        from app.worker.tasks import _execute_tool_task_impl
        return await _execute_tool_task_impl(task_id, params)


def get_task_executor():
    """
    获取任务执行器

    开发模式返回同步执行器，生产模式返回 Celery
    """
    if settings.CELERY_BROKER_URL:
        return celery_app
    return SyncTaskExecutor()
