# backend/app/tasks/queue_manager.py
"""任务队列管理器

根据详细设计说明书 4.3 节实现。
负责任务队列的选择、入队和状态查询。
"""

from enum import Enum
from datetime import UTC, datetime
from typing import Any, Dict, Optional, TYPE_CHECKING
import logging

from app.common.time import utcnow

if TYPE_CHECKING:
    from celery import Task as CeleryTask

logger = logging.getLogger(__name__)


class TaskQueue(str, Enum):
    """任务队列枚举"""
    HIGH_PRIORITY = "high_priority"
    GPU_QUEUE = "gpu_queue"
    HEAVY_COMPUTE_QUEUE = "heavy_compute"
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
        TaskQueue.HEAVY_COMPUTE_QUEUE.value: 4,
        TaskQueue.CPU_QUEUE.value: 3,
        TaskQueue.DEFAULT.value: 1
    }

    # 管理员可以使用高优先级队列。
    PRIVILEGED_ROLES = {"admin"}
    AGING_INTERVAL_SECONDS = 300
    MAX_CELERY_PRIORITY = 9

    @classmethod
    def determine_queue(
        cls,
        tool_config: Dict[str, Any],
        user_role: Optional[str] = None,
        priority: Optional[str] = None,
        gpu_required: Optional[bool] = None,
    ) -> str:
        """确定任务队列

        根据工具配置、用户角色和任务优先级确定应使用的队列。

        Args:
            tool_config: 工具配置
            user_role: 用户角色
            priority: 任务优先级 (high/normal/low)
            gpu_required: Tool 模型中的 GPU 要求（优先于版本配置）

        Returns:
            str: 队列名称
        """
        # 1. 高优先级任务或管理员
        if priority == "high" or (user_role and user_role.lower() in cls.PRIVILEGED_ROLES):
            return TaskQueue.HIGH_PRIORITY.value

        # 2. GPU任务
        if gpu_required if gpu_required is not None else tool_config.get("gpu_required", False):
            return TaskQueue.GPU_QUEUE.value

        # 3. 重型CPU任务进入独立队列，供专用 worker 或未来集群适配器消费。
        resource_profile = tool_config.get("resource_profile")
        if isinstance(resource_profile, dict):
            tier = str(resource_profile.get("tier") or "").strip().lower()
            if tier == "heavy":
                return TaskQueue.HEAVY_COMPUTE_QUEUE.value

        # 4. 普通CPU任务
        if tool_config.get("type") in ["docker_image", "python_script", "ssh_job", "k8s_job"]:
            return TaskQueue.CPU_QUEUE.value

        # 5. 默认队列（API调用等）
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

    @staticmethod
    def get_wait_seconds(
        created_at: Optional[datetime],
        *,
        now: Optional[datetime] = None,
    ) -> int:
        """计算任务已等待秒数，未来时间按 0 处理。"""
        if not isinstance(created_at, datetime):
            return 0

        current = now or utcnow()
        if created_at.tzinfo is not None:
            created_at = created_at.astimezone(UTC).replace(tzinfo=None)
        if current.tzinfo is not None:
            current = current.astimezone(UTC).replace(tzinfo=None)
        return max(int((current - created_at).total_seconds()), 0)

    @classmethod
    def get_dispatch_priority_details(
        cls,
        queue: str,
        *,
        task_priority: Optional[str] = None,
        created_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> dict[str, int]:
        """返回基础队列优先级叠加等待时间后的最终调度优先级。"""
        base_priority = cls.get_queue_priority(queue)
        if task_priority == "high":
            base_priority = max(base_priority, cls.MAX_CELERY_PRIORITY)

        wait_seconds = cls.get_wait_seconds(created_at, now=now)
        aging_boost = wait_seconds // cls.AGING_INTERVAL_SECONDS
        priority = min(base_priority + aging_boost, cls.MAX_CELERY_PRIORITY)
        return {
            "priority": priority,
            "wait_seconds": wait_seconds,
            "priority_boost": priority - base_priority,
        }

    @classmethod
    def get_dispatch_priority(
        cls,
        queue: str,
        *,
        task_priority: Optional[str] = None,
        created_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> int:
        """返回 Celery enqueue 使用的最终优先级。"""
        return cls.get_dispatch_priority_details(
            queue,
            task_priority=task_priority,
            created_at=created_at,
            now=now,
        )["priority"]

    @classmethod
    def enqueue_task(
        cls,
        task_id: str,
        tool_version_id: str,
        queue: str,
        attempt_id: Optional[str] = None,
        countdown: int = 0,
        eta: Optional[Any] = None,
        priority: Optional[int] = None,
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

        priority = (
            min(max(int(priority), 0), cls.MAX_CELERY_PRIORITY)
            if priority is not None
            else cls.get_queue_priority(queue)
        )

        logger.info(
            f"Enqueuing task {task_id} to queue '{queue}' with priority {priority}",
            extra={
                "task_id": task_id,
                "tool_version_id": tool_version_id,
                "queue": queue,
                "priority": priority
            }
        )

        task_args = [task_id, tool_version_id]
        if attempt_id is not None:
            task_args.append(attempt_id)

        celery_task = celery_app.send_task(
            "app.worker.tasks.execute_tool_task",
            args=task_args,
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
        for tasks in active_tasks.values():
            for task in tasks:
                queue = task.get("delivery_info", {}).get("routing_key", "default")
                if queue in queue_stats:
                    queue_stats[queue]["active"] += 1

        # 统计预留任务
        for tasks in reserved_tasks.values():
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
            TaskQueue.HEAVY_COMPUTE_QUEUE.value: 900,
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
            for tasks in reserved.values():
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
