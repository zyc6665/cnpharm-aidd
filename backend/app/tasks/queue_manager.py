# backend/app/tasks/queue_manager.py
"""任务队列管理器

根据详细设计说明书 4.3 节实现。
负责任务队列的选择、入队和状态查询。
"""

from enum import Enum
from typing import Any, Dict, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from celery import Task as CeleryTask

logger = logging.getLogger(__name__)


class TaskQueue(str, Enum):
    """任务队列枚举"""
    HIGH_PRIORITY = "high_priority"
    GPU_QUEUE = "gpu_queue"
    CPU_QUEUE = "cpu_queue"
    DEFAULT = "default"


class TaskQueueManager:
    """任务队列管理器

    负责：
    1. 根据工具配置和用户角色确定任务队列
    2. 将任务加入Celery队列
    3. 查询队列状态
    """

    # 队列优先级映射（数字越大优先级越高）
    QUEUE_PRIORITY: Dict[str, int] = {
        TaskQueue.HIGH_PRIORITY.value: 9,
        TaskQueue.GPU_QUEUE.value: 5,
        TaskQueue.CPU_QUEUE.value: 3,
        TaskQueue.DEFAULT.value: 1
    }

    # VIP/管理员角色列表
    VIP_ROLES = {"vip", "admin", "super_admin"}

    @classmethod
    def determine_queue(
        cls,
        tool_config: Dict[str, Any],
        user_role: Optional[str] = None,
        priority: Optional[str] = None
    ) -> str:
        """确定任务队列

        根据工具配置、用户角色和任务优先级确定应使用的队列。

        Args:
            tool_config: 工具配置
            user_role: 用户角色
            priority: 任务优先级 (high/normal/low)

        Returns:
            str: 队列名称
        """
        # 1. 高优先级任务或VIP用户
        if priority == "high" or (user_role and user_role.lower() in cls.VIP_ROLES):
            return TaskQueue.HIGH_PRIORITY.value

        # 2. GPU任务
        if tool_config.get("gpu_required", False):
            return TaskQueue.GPU_QUEUE.value

        # 3. 普通CPU任务
        if tool_config.get("type") in ["docker_image", "python_script"]:
            return TaskQueue.CPU_QUEUE.value

        # 4. 默认队列（API调用等）
        return TaskQueue.DEFAULT.value

    @classmethod
    def get_queue_priority(cls, queue: str) -> int:
        """获取队列优先级

        Args:
            queue: 队列名称

        Returns:
            int: 优先级值
        """
        return cls.QUEUE_PRIORITY.get(queue, 1)

    @classmethod
    def enqueue_task(
        cls,
        task_id: str,
        tool_version_id: str,
        queue: str,
        countdown: int = 0,
        eta: Optional[Any] = None
    ) -> "CeleryTask":
        """将任务加入队列

        Args:
            task_id: 任务ID
            tool_version_id: 工具版本ID
            queue: 队列名称
            countdown: 延迟执行秒数
            eta: 预定执行时间

        Returns:
            CeleryTask: Celery任务对象
        """
        from app.worker.celery_app import celery_app

        priority = cls.get_queue_priority(queue)

        logger.info(
            f"Enqueuing task {task_id} to queue '{queue}' with priority {priority}",
            extra={
                "task_id": task_id,
                "tool_version_id": tool_version_id,
                "queue": queue,
                "priority": priority
            }
        )

        celery_task = celery_app.send_task(
            "app.worker.tasks.execute_tool_task",
            args=[task_id, tool_version_id],
            queue=queue,
            priority=priority,
            countdown=countdown,
            eta=eta
        )

        return celery_task

    @classmethod
    async def get_queue_status(cls) -> Dict[str, Any]:
        """获取队列状态

        Returns:
            Dict[str, Any]: 队列状态信息
        """
        from app.worker.celery_app import celery_app

        try:
            inspect = celery_app.control.inspect()

            # 获取活跃任务
            active_tasks = inspect.active() or {}

            # 获取预留任务（已分配但未执行）
            reserved_tasks = inspect.reserved() or {}

            # 获取调度任务
            scheduled_tasks = inspect.scheduled() or {}

            # 统计各队列任务数
            queue_stats = cls._calculate_queue_stats(active_tasks, reserved_tasks)

            # 获取Worker信息
            worker_stats = cls._get_worker_stats(inspect)

            return {
                "active_workers": len(active_tasks),
                "active_tasks": sum(len(t) for t in active_tasks.values()),
                "reserved_tasks": sum(len(t) for t in reserved_tasks.values()),
                "scheduled_tasks": sum(len(t) for t in scheduled_tasks.values()),
                "queue_stats": queue_stats,
                "worker_stats": worker_stats,
                "status": "healthy"
            }

        except Exception as e:
            logger.error(f"Failed to get queue status: {e}")
            return {
                "active_workers": 0,
                "active_tasks": 0,
                "reserved_tasks": 0,
                "scheduled_tasks": 0,
                "queue_stats": {},
                "worker_stats": {},
                "status": "error",
                "error": str(e)
            }

    @classmethod
    def _calculate_queue_stats(
        cls,
        active_tasks: Dict[str, list],
        reserved_tasks: Dict[str, list]
    ) -> Dict[str, Dict[str, int]]:
        """计算各队列统计"""
        queue_stats = {
            queue.value: {"active": 0, "reserved": 0}
            for queue in TaskQueue
        }

        # 统计活跃任务
        for worker, tasks in active_tasks.items():
            for task in tasks:
                queue = task.get("delivery_info", {}).get("routing_key", "default")
                if queue in queue_stats:
                    queue_stats[queue]["active"] += 1

        # 统计预留任务
        for worker, tasks in reserved_tasks.items():
            for task in tasks:
                queue = task.get("delivery_info", {}).get("routing_key", "default")
                if queue in queue_stats:
                    queue_stats[queue]["reserved"] += 1

        return queue_stats

    @classmethod
    def _get_worker_stats(cls, inspect) -> Dict[str, Any]:
        """获取Worker统计"""
        try:
            stats = inspect.stats() or {}
            ping = inspect.ping() or {}

            workers = {}
            for worker_name, worker_stats in stats.items():
                workers[worker_name] = {
                    "status": "online" if worker_name in ping else "offline",
                    "concurrency": worker_stats.get("pool", {}).get("max-concurrency", 0),
                    "processes": worker_stats.get("pool", {}).get("processes", []),
                    "prefetch_count": worker_stats.get("prefetch_count", 0)
                }

            return workers

        except Exception as e:
            logger.warning(f"Failed to get worker stats: {e}")
            return {}

    @classmethod
    def revoke_task(
        cls,
        celery_task_id: str,
        terminate: bool = False,
        signal: str = "SIGTERM"
    ) -> bool:
        """撤销任务

        Args:
            celery_task_id: Celery任务ID
            terminate: 是否强制终止
            signal: 终止信号

        Returns:
            bool: 是否成功
        """
        from app.worker.celery_app import celery_app

        try:
            celery_app.control.revoke(
                celery_task_id,
                terminate=terminate,
                signal=signal
            )
            logger.info(f"Revoked task {celery_task_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to revoke task {celery_task_id}: {e}")
            return False

    @classmethod
    def get_task_result(cls, celery_task_id: str) -> Dict[str, Any]:
        """获取任务结果

        Args:
            celery_task_id: Celery任务ID

        Returns:
            Dict[str, Any]: 任务结果信息
        """
        from celery.result import AsyncResult
        from app.worker.celery_app import celery_app

        result = AsyncResult(celery_task_id, app=celery_app)

        return {
            "task_id": celery_task_id,
            "status": result.status,
            "result": result.result if result.ready() else None,
            "traceback": result.traceback if result.failed() else None,
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else None
        }

    @classmethod
    async def get_estimated_wait_time(cls, queue: str) -> int:
        """估算队列等待时间

        Args:
            queue: 队列名称

        Returns:
            int: 预计等待秒数
        """
        status = await cls.get_queue_status()
        queue_stats = status.get("queue_stats", {}).get(queue, {})

        # 获取队列中的任务数
        pending_tasks = queue_stats.get("reserved", 0)

        # 根据队列类型估算平均执行时间
        avg_execution_time = {
            TaskQueue.HIGH_PRIORITY.value: 60,
            TaskQueue.GPU_QUEUE.value: 300,
            TaskQueue.CPU_QUEUE.value: 120,
            TaskQueue.DEFAULT.value: 30
        }.get(queue, 60)

        # 估算等待时间
        active_workers = status.get("active_workers", 1) or 1
        estimated_wait = (pending_tasks * avg_execution_time) // active_workers

        return estimated_wait

    @classmethod
    def get_queue_position(cls, task_id: str, queue: str) -> int:
        """获取任务在队列中的位置

        Args:
            task_id: 任务ID
            queue: 队列名称

        Returns:
            int: 队列位置（从1开始，-1表示不在队列中）
        """
        from app.worker.celery_app import celery_app

        try:
            inspect = celery_app.control.inspect()
            reserved = inspect.reserved() or {}

            position = 0
            for worker, tasks in reserved.items():
                for task in tasks:
                    task_queue = task.get("delivery_info", {}).get("routing_key", "default")
                    if task_queue == queue:
                        position += 1
                        if task.get("args", [None])[0] == task_id:
                            return position

            return -1

        except Exception as e:
            logger.error(f"Failed to get queue position: {e}")
            return -1
