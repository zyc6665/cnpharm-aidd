# backend/app/gpu/shortage_handler.py
"""GPU资源不足处理模块

根据详细设计说明书 8.2 节实现。
处理GPU资源不足时的任务调度和用户通知。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import asyncio
import logging

logger = logging.getLogger(__name__)


class ShortageAction(str, Enum):
    """资源不足处理动作"""
    QUEUE = "queue"                 # 排队等待
    CPU_FALLBACK = "cpu_fallback"   # 降级到CPU
    REJECT = "reject"               # 拒绝任务
    DEFER = "defer"                 # 延迟执行
    NOTIFY = "notify"               # 通知用户


class QueuePriority(str, Enum):
    """队列优先级"""
    VIP = "vip"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class QueuePosition:
    """队列位置信息"""
    task_id: str
    position: int
    estimated_wait_minutes: int
    priority: QueuePriority
    queued_at: datetime
    gpu_memory_required: int        # MB
    tool_name: str


@dataclass
class ShortageStatus:
    """GPU资源不足状态"""
    has_shortage: bool
    available_gpus: int
    total_gpus: int
    waiting_tasks: int
    estimated_wait_minutes: int
    recommended_action: ShortageAction
    message: str


@dataclass
class WaitingTask:
    """等待中的任务"""
    task_id: str
    user_id: str
    tool_id: str
    priority: QueuePriority
    queued_at: datetime
    gpu_memory_required: int
    supports_cpu_fallback: bool = False
    retry_count: int = 0
    max_wait_minutes: int = 60


class GPUShortageHandler:
    """GPU资源不足处理器

    负责处理GPU资源不足时的任务调度策略。
    """

    # 队列优先级权重
    PRIORITY_WEIGHTS = {
        QueuePriority.VIP: 4,
        QueuePriority.HIGH: 3,
        QueuePriority.NORMAL: 2,
        QueuePriority.LOW: 1
    }

    # 默认配置
    DEFAULT_MAX_QUEUE_SIZE = 100
    DEFAULT_MAX_WAIT_MINUTES = 60
    DEFAULT_ESTIMATION_FACTOR = 5  # 每个任务预估5分钟

    def __init__(
        self,
        max_queue_size: int = None,
        max_wait_minutes: int = None,
        enable_cpu_fallback: bool = True,
        notify_threshold_minutes: int = 30
    ):
        """初始化处理器

        Args:
            max_queue_size: 最大队列长度
            max_wait_minutes: 最大等待时间（分钟）
            enable_cpu_fallback: 是否启用CPU降级
            notify_threshold_minutes: 通知阈值（分钟）
        """
        self.max_queue_size = max_queue_size or self.DEFAULT_MAX_QUEUE_SIZE
        self.max_wait_minutes = max_wait_minutes or self.DEFAULT_MAX_WAIT_MINUTES
        self.enable_cpu_fallback = enable_cpu_fallback
        self.notify_threshold_minutes = notify_threshold_minutes

        # 等待队列（内存存储，生产环境应使用Redis）
        self._waiting_queue: List[WaitingTask] = []
        self._notified_users: Dict[str, datetime] = {}  # 已通知用户

    async def handle_no_gpu_available(
        self,
        task_id: str,
        user_id: str,
        tool_id: str,
        tool_config: Dict[str, Any],
        priority: QueuePriority = QueuePriority.NORMAL
    ) -> Tuple[ShortageAction, Dict[str, Any]]:
        """处理无可用GPU的情况

        Args:
            task_id: 任务ID
            user_id: 用户ID
            tool_id: 工具ID
            tool_config: 工具配置
            priority: 任务优先级

        Returns:
            Tuple[ShortageAction, Dict]: (处理动作, 附加信息)
        """
        logger.info(f"Handling GPU shortage for task {task_id}")

        # 获取当前队列状态
        queue_position = len(self._waiting_queue)
        estimated_wait = queue_position * self.DEFAULT_ESTIMATION_FACTOR

        # 检查是否支持CPU降级
        supports_cpu = tool_config.get("supports_cpu_fallback", False)
        gpu_memory_required = tool_config.get("gpu_memory_mb", 4096)

        # 决策逻辑
        if queue_position >= self.max_queue_size:
            # 队列已满
            if supports_cpu and self.enable_cpu_fallback:
                logger.info(f"Task {task_id}: Queue full, falling back to CPU")
                return ShortageAction.CPU_FALLBACK, {
                    "reason": "GPU queue is full",
                    "original_requirement": "gpu",
                    "fallback_mode": "cpu"
                }
            else:
                logger.warning(f"Task {task_id}: Queue full, rejecting task")
                return ShortageAction.REJECT, {
                    "reason": "GPU queue is full and CPU fallback not supported",
                    "queue_size": queue_position,
                    "max_queue_size": self.max_queue_size
                }

        if estimated_wait > self.max_wait_minutes:
            # 等待时间过长
            if supports_cpu and self.enable_cpu_fallback:
                logger.info(f"Task {task_id}: Wait time too long, falling back to CPU")
                return ShortageAction.CPU_FALLBACK, {
                    "reason": "Estimated wait time exceeds limit",
                    "estimated_wait_minutes": estimated_wait,
                    "max_wait_minutes": self.max_wait_minutes
                }

        # 加入等待队列
        waiting_task = WaitingTask(
            task_id=task_id,
            user_id=user_id,
            tool_id=tool_id,
            priority=priority,
            queued_at=datetime.utcnow(),
            gpu_memory_required=gpu_memory_required,
            supports_cpu_fallback=supports_cpu
        )
        self._add_to_queue(waiting_task)

        # 获取实际队列位置
        position = self._get_queue_position(task_id)

        logger.info(f"Task {task_id}: Queued at position {position}")

        return ShortageAction.QUEUE, {
            "queue_position": position,
            "estimated_wait_minutes": position * self.DEFAULT_ESTIMATION_FACTOR,
            "supports_cpu_fallback": supports_cpu
        }

    def _add_to_queue(self, task: WaitingTask) -> None:
        """添加任务到等待队列（按优先级排序）

        Args:
            task: 等待任务
        """
        # 找到插入位置
        insert_index = len(self._waiting_queue)
        task_weight = self.PRIORITY_WEIGHTS[task.priority]

        for i, existing in enumerate(self._waiting_queue):
            existing_weight = self.PRIORITY_WEIGHTS[existing.priority]
            if task_weight > existing_weight:
                insert_index = i
                break

        self._waiting_queue.insert(insert_index, task)

    def _get_queue_position(self, task_id: str) -> int:
        """获取任务在队列中的位置

        Args:
            task_id: 任务ID

        Returns:
            int: 队列位置（从1开始）
        """
        for i, task in enumerate(self._waiting_queue):
            if task.task_id == task_id:
                return i + 1
        return -1

    async def get_queue_position(self, task_id: str) -> Optional[QueuePosition]:
        """获取任务队列位置详情

        Args:
            task_id: 任务ID

        Returns:
            Optional[QueuePosition]: 队列位置信息
        """
        position = self._get_queue_position(task_id)
        if position < 0:
            return None

        task = self._waiting_queue[position - 1]

        return QueuePosition(
            task_id=task_id,
            position=position,
            estimated_wait_minutes=position * self.DEFAULT_ESTIMATION_FACTOR,
            priority=task.priority,
            queued_at=task.queued_at,
            gpu_memory_required=task.gpu_memory_required,
            tool_name=task.tool_id
        )

    async def remove_from_queue(self, task_id: str) -> bool:
        """从队列中移除任务

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功移除
        """
        for i, task in enumerate(self._waiting_queue):
            if task.task_id == task_id:
                del self._waiting_queue[i]
                logger.info(f"Task {task_id} removed from queue")
                return True
        return False

    async def get_next_task(self) -> Optional[WaitingTask]:
        """获取下一个待执行的任务

        Returns:
            Optional[WaitingTask]: 下一个任务
        """
        if not self._waiting_queue:
            return None

        task = self._waiting_queue.pop(0)
        logger.info(f"Task {task.task_id} dequeued for execution")
        return task

    async def check_long_waiting_tasks(self) -> List[WaitingTask]:
        """检查等待时间过长的任务

        Returns:
            List[WaitingTask]: 等待过长的任务列表
        """
        now = datetime.utcnow()
        long_waiting = []

        for task in self._waiting_queue:
            wait_time = (now - task.queued_at).total_seconds() / 60
            if wait_time >= self.notify_threshold_minutes:
                long_waiting.append(task)

        return long_waiting

    async def notify_long_waiting_users(self) -> List[str]:
        """通知等待时间过长的用户

        Returns:
            List[str]: 已通知的用户ID列表
        """
        long_waiting = await self.check_long_waiting_tasks()
        notified = []
        now = datetime.utcnow()

        for task in long_waiting:
            # 检查是否已在一小时内通知过
            last_notified = self._notified_users.get(task.user_id)
            if last_notified and (now - last_notified).total_seconds() < 3600:
                continue

            # 发送通知
            await self._send_notification(
                user_id=task.user_id,
                task_id=task.task_id,
                wait_minutes=int((now - task.queued_at).total_seconds() / 60),
                position=self._get_queue_position(task.task_id)
            )

            self._notified_users[task.user_id] = now
            notified.append(task.user_id)

        return notified

    async def _send_notification(
        self,
        user_id: str,
        task_id: str,
        wait_minutes: int,
        position: int
    ) -> None:
        """发送通知给用户

        Args:
            user_id: 用户ID
            task_id: 任务ID
            wait_minutes: 已等待分钟数
            position: 队列位置
        """
        # 实际实现应该调用通知服务
        logger.info(
            f"Notification sent to user {user_id}: "
            f"Task {task_id} has been waiting for {wait_minutes} minutes, "
            f"current position: {position}"
        )

    async def get_shortage_status(self) -> ShortageStatus:
        """获取GPU资源不足状态

        Returns:
            ShortageStatus: 状态信息
        """
        from app.gpu.detector import get_gpu_detector

        detector = get_gpu_detector()
        node_info = await detector.get_node_info()

        available_gpus = 0
        total_gpus = 0

        if node_info:
            total_gpus = node_info.gpu_count
            # 简化：假设利用率低于80%的GPU视为可用
            stats = await detector.get_gpu_stats()
            for stat in stats:
                if stat.utilization < 80:
                    available_gpus += 1

        waiting_tasks = len(self._waiting_queue)
        estimated_wait = waiting_tasks * self.DEFAULT_ESTIMATION_FACTOR

        has_shortage = available_gpus == 0 and waiting_tasks > 0

        if not has_shortage:
            recommended_action = ShortageAction.QUEUE
            message = "GPU resources available"
        elif waiting_tasks > self.max_queue_size * 0.8:
            recommended_action = ShortageAction.CPU_FALLBACK
            message = "GPU queue is nearly full, consider CPU fallback"
        elif estimated_wait > self.max_wait_minutes * 0.8:
            recommended_action = ShortageAction.DEFER
            message = "High wait time expected, consider deferring"
        else:
            recommended_action = ShortageAction.QUEUE
            message = "GPU resources temporarily unavailable, queued"

        return ShortageStatus(
            has_shortage=has_shortage,
            available_gpus=available_gpus,
            total_gpus=total_gpus,
            waiting_tasks=waiting_tasks,
            estimated_wait_minutes=estimated_wait,
            recommended_action=recommended_action,
            message=message
        )

    async def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息

        Returns:
            Dict: 统计信息
        """
        now = datetime.utcnow()
        priority_counts = {p.value: 0 for p in QueuePriority}
        total_wait_time = 0

        for task in self._waiting_queue:
            priority_counts[task.priority.value] += 1
            total_wait_time += (now - task.queued_at).total_seconds()

        avg_wait_time = total_wait_time / len(self._waiting_queue) if self._waiting_queue else 0

        return {
            "total_waiting": len(self._waiting_queue),
            "by_priority": priority_counts,
            "average_wait_seconds": avg_wait_time,
            "max_queue_size": self.max_queue_size,
            "queue_utilization": len(self._waiting_queue) / self.max_queue_size * 100
        }

    async def cleanup_expired_tasks(self) -> List[str]:
        """清理过期的等待任务

        Returns:
            List[str]: 被清理的任务ID列表
        """
        now = datetime.utcnow()
        expired = []
        remaining = []

        for task in self._waiting_queue:
            wait_minutes = (now - task.queued_at).total_seconds() / 60
            if wait_minutes > task.max_wait_minutes:
                expired.append(task.task_id)
                logger.warning(f"Task {task.task_id} expired after waiting {wait_minutes:.1f} minutes")
            else:
                remaining.append(task)

        self._waiting_queue = remaining
        return expired


# 全局实例
_shortage_handler: Optional[GPUShortageHandler] = None


def get_shortage_handler() -> GPUShortageHandler:
    """获取GPU资源不足处理器单例

    Returns:
        GPUShortageHandler: 处理器实例
    """
    global _shortage_handler
    if _shortage_handler is None:
        _shortage_handler = GPUShortageHandler()
    return _shortage_handler
