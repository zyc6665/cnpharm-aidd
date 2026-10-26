"""任务状态 SSE 事件流（docs/05 §1.5、§9；docs/10 API-08）。

契约：``GET /api/v1/tasks/{task_id}/events`` 返回 ``text/event-stream``。

事件类型：
- ``snapshot``：连接建立后立即下发的一次权威快照（状态/进度/消息/时间戳）。
- ``status``：任务状态变化。
- ``progress``：进度或进度消息变化。
- ``heartbeat``：心跳（默认 15s），防止中间代理按空闲超时断开。
- ``done``：任务进入终态，随后服务端主动关闭流。

为什么用「进程内广播 + 数据库回读」而不是消息队列：
1. 数据库是唯一真值（docs/04 §3.2.2）。回读天然免疫丢事件、Redis 重启
   （HA-T-06：Redis 重启后 SSE 自动重连、进度不丢）与跨副本问题。
2. 同进程广播只负责把「下一次回读」从 1s 提前到 1ms，不承担正确性。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.common.task_status import task_status_to_api
from app.models.tasks import Task, TaskLog, TaskStatus
from app.services.task_event_hub import TaskEventHub, get_task_event_hub

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {
    TaskStatus.SUCCESS.value,
    TaskStatus.FAILURE.value,
    TaskStatus.CANCELED.value,
    TaskStatus.TIMEOUT.value,
}

EVENT_SNAPSHOT = "snapshot"
EVENT_STATUS = "status"
EVENT_PROGRESS = "progress"
EVENT_LOG = "log"
EVENT_HEARTBEAT = "heartbeat"
EVENT_DONE = "done"


@dataclass(frozen=True)
class TaskEventState:
    """一次回读得到的任务可观测状态。"""

    status: Optional[str]
    progress: float
    progress_message: Optional[str]
    error_message: Optional[str]
    updated_at: Optional[datetime]

    @property
    def terminal(self) -> bool:
        return (self.status or "").upper() in TERMINAL_STATUSES

    def to_payload(self, task_id: str) -> Dict[str, Any]:
        return {
            "taskId": task_id,
            "status": task_status_to_api(self.status),
            "rawStatus": self.status,
            "progress": self.progress,
            "progressMessage": self.progress_message,
            "errorMessage": self.error_message,
            "updatedAt": _iso(self.updated_at),
            "terminal": self.terminal,
        }


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else None


def state_from_task(task: Task) -> TaskEventState:
    return TaskEventState(
        status=task.status,
        progress=float(task.progress or 0.0),
        progress_message=task.progress_message,
        error_message=task.error_message,
        updated_at=task.updated_at or task.created_at,
    )


def format_sse(event: str, data: Dict[str, Any], *, event_id: Optional[str] = None) -> str:
    """按 SSE 规范拼帧：``id:`` / ``event:`` / ``data:`` / 空行。"""
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    payload = json.dumps(data, ensure_ascii=False, default=str)
    for chunk in payload.splitlines() or [""]:
        lines.append(f"data: {chunk}")
    return "\n".join(lines) + "\n\n"


def format_heartbeat() -> str:
    """注释帧：不产生事件，只保活。"""
    return ": ping\n\n"


def describe_delta(
    previous: Optional[TaskEventState],
    current: TaskEventState,
) -> Optional[str]:
    """比较两次回读，返回需要下发的事件类型；无变化返回 None。"""
    if previous is None:
        return EVENT_SNAPSHOT
    if previous.status != current.status:
        return EVENT_STATUS
    if previous.progress != current.progress or previous.progress_message != current.progress_message:
        return EVENT_PROGRESS
    if previous.error_message != current.error_message:
        return EVENT_STATUS
    return None


async def load_state(db: AsyncSession, task_id: str) -> Optional[TaskEventState]:
    result = await db.execute(
        select(Task.status, Task.progress, Task.progress_message, Task.error_message, Task.updated_at, Task.created_at).where(
            Task.id == task_id
        )
    )
    row = result.first()
    if row is None:
        return None
    return TaskEventState(
        status=row[0],
        progress=float(row[1] or 0.0),
        progress_message=row[2],
        error_message=row[3],
        updated_at=row[4] or row[5],
    )


async def load_new_logs(
    db: AsyncSession,
    *,
    task_id: str,
    after: datetime,
    limit: int = 20,
) -> list[TaskLog]:
    result = await db.execute(
        select(TaskLog)
        .where(TaskLog.task_id == task_id, TaskLog.timestamp > after)
        .order_by(TaskLog.timestamp.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


def serialize_log(log: TaskLog) -> Dict[str, Any]:
    return {
        "id": log.id,
        "taskId": log.task_id,
        "level": log.level,
        "message": log.message,
        "timestamp": _iso(log.timestamp),
    }


async def stream_task_events(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    task_id: str,
    initial: TaskEventState,
    poll_interval_seconds: float = 1.0,
    heartbeat_seconds: float = 15.0,
    max_duration_seconds: Optional[float] = 1800.0,
    include_logs: bool = True,
    hub: Optional[TaskEventHub] = None,
) -> AsyncIterator[str]:
    """生成 SSE 帧序列。

    每个连接独立回读数据库，因此多副本、多 worker 下不需要任何跨进程协调。
    ``hub`` 命中时立即唤醒，未命中时最迟 ``poll_interval_seconds`` 后收敛。
    """
    hub = hub or get_task_event_hub()
    queue = hub.subscribe(task_id)
    sequence = 0
    state = initial
    last_log_at = datetime.min
    loop = asyncio.get_running_loop()
    started = loop.time()

    try:
        sequence += 1
        yield format_sse(EVENT_SNAPSHOT, state.to_payload(task_id), event_id=str(sequence))

        if state.terminal:
            yield format_sse(EVENT_DONE, state.to_payload(task_id), event_id=str(sequence + 1))
            return

        idle_seconds = 0.0
        wait_seconds = min(poll_interval_seconds, heartbeat_seconds)
        while True:
            try:
                await asyncio.wait_for(queue.get(), timeout=wait_seconds)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                raise

            async with session_factory() as db:
                current = await load_state(db, task_id)
                if current is None:
                    yield format_sse(
                        EVENT_STATUS,
                        {"taskId": task_id, "status": None, "errorMessage": "任务已不存在", "terminal": True},
                        event_id=str(sequence + 1),
                    )
                    return

                changed = describe_delta(state, current)
                if changed is not None:
                    sequence += 1
                    state = current
                    idle_seconds = 0.0
                    yield format_sse(changed, state.to_payload(task_id), event_id=str(sequence))
                else:
                    idle_seconds += wait_seconds

                if include_logs:
                    for log in await load_new_logs(db, task_id=task_id, after=last_log_at):
                        sequence += 1
                        last_log_at = log.timestamp or last_log_at
                        yield format_sse(EVENT_LOG, serialize_log(log), event_id=str(sequence))

                if state.terminal:
                    sequence += 1
                    yield format_sse(EVENT_DONE, state.to_payload(task_id), event_id=str(sequence))
                    return

            if idle_seconds >= heartbeat_seconds:
                idle_seconds = 0.0
                yield format_heartbeat()

            if max_duration_seconds is not None:
                elapsed = loop.time() - started
                if elapsed >= max_duration_seconds:
                    # 长时任务（MD 数小时）不能占着连接不放，转由前端重连续订。
                    yield format_heartbeat()
                    return
    finally:
        hub.unsubscribe(task_id, queue)
