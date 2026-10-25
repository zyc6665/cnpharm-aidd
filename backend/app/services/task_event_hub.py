"""任务事件进程内广播中枢（SSE 的快速通道）。

为什么需要它：``GET /api/v1/tasks/{id}/events`` 要把状态变化推给浏览器，但
worker 与 API 可能是同一个进程（direct 执行）也可能是不同进程（celery）。
本模块只解决「同进程内即时唤醒」，跨进程与漏事件由 SSE 生成器周期性回读
数据库兜底——数据库是唯一真值（docs/04 §3.2.2「状态以库为准」）。

设计约束：
- ``publish`` 绝不阻塞、绝不抛异常：任务主流程不能因为没人订阅或队列满而受影响。
- 订阅者队列有上限，满了直接丢弃最旧事件：SSE 消费方拿到的是「有变化」的信号，
  真正的字段值永远从数据库重新读，丢一条信号不会丢状态。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)

DEFAULT_SUBSCRIBER_QUEUE_SIZE = 32


class TaskEventHub:
    """单进程内的任务事件订阅表。"""

    def __init__(self, *, queue_size: int = DEFAULT_SUBSCRIBER_QUEUE_SIZE) -> None:
        self._queue_size = queue_size
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue:
        """为一个 SSE 连接注册队列。调用方必须在结束时 unsubscribe。"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.setdefault(task_id, set()).add(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        queues = self._subscribers.get(task_id)
        if not queues:
            return
        queues.discard(queue)
        if not queues:
            self._subscribers.pop(task_id, None)

    def publish(self, task_id: str, event: Dict[str, Any]) -> int:
        """把事件投递给该任务的所有订阅者，返回实际投递数。"""
        queues = self._subscribers.get(task_id)
        if not queues:
            return 0
        delivered = 0
        for queue in list(queues):
            try:
                queue.put_nowait(event)
                delivered += 1
            except asyncio.QueueFull:
                # 丢信号不丢状态：消费方下一轮回读数据库仍能收敛到最新值。
                logger.debug("任务事件队列已满，丢弃一条通知: task=%s", task_id)
        return delivered

    def subscriber_count(self, task_id: str) -> int:
        return len(self._subscribers.get(task_id) or ())

    def total_subscribers(self) -> int:
        """当前进程内所有 SSE 订阅者数量（供系统统计展示）。"""
        return sum(len(queues) for queues in self._subscribers.values())

    def clear(self) -> None:
        self._subscribers.clear()


_hub: TaskEventHub | None = None


def get_task_event_hub() -> TaskEventHub:
    """返回进程级单例。"""
    global _hub
    if _hub is None:
        _hub = TaskEventHub()
    return _hub
