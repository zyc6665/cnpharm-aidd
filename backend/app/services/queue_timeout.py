"""排队超时判定（docs/18 §6.4 B-2b）。

为什么需要这个巡检
------------------
步骤 13 补齐 `QUEUED` 状态后，`TaskStateMachine.TRANSITIONS` 里就有
`QUEUED -> TIMEOUT` 这条边，但**没有任何东西去用它**：超时判定只在执行器层
（任务已经开始跑、`timeout_sec` 到期），排队阶段完全没有上限。

后果是队列一旦停止消费——调度器漏消息、卡位全占、配额被别人占死、集群掉卡——
任务会永远停在 `QUEUED`，页面显示「排队中」而实际永远不会开始。用户看不到失败，
也就不会重试；运维看队列深度正常（因为任务确实在队列里），更难发现。
这类「安静地卡住」比直接失败更难排查，所以必须有与用户行为无关的兜底。

锚点取哪个时间
--------------
取任务进入排队的那一刻（`extra_data["queued_at"]`，由 `TaskStateMachine` 在
转入 `QUEUED` 时写入）。不用 `created_at`：任务可能先 `PENDING` 停留（等上传物化、
等前置校验），那段时间不该算排队。也不用 `updated_at` 兜底优先——它会被任何一次
写操作刷新，正常排队期间虽然不动，但语义上不是「入队时刻」。

历史数据没有 `queued_at` 时退化用 `updated_at`：老任务的 `updated_at` 就是它最后
一次状态变更（即入队）的时间，在本巡检的场景下等价，且不会因为缺少新字段而漏判。

为什么复用 `mark_timeout` 而不是直接改 `task.status`
--------------------------------------------------
`docs/04 §9.1` 要求状态迁移一律走状态机（CAS），`test/test_worker_state_machine.py`
还有一条 AST 守卫禁止业务代码直接给 `task.status` 赋值。`mark_timeout` 会顺带写入
`finished_at`、`error_message`、`execution_time_sec`，这些是验收要看的时间线字段。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.config import settings
from app.models.tasks import Task, TaskLog, TaskStatus
from app.tasks.resource_lease import release_task_resource_reservation
from app.tasks.state_machine import TaskStateMachine

logger = logging.getLogger(__name__)

QUEUED_ANCHOR_KEY = "queued_at"
QUEUED_TIMEOUT_LOG_LEVEL = "WARNING"


def _parse_anchor(value: Any) -> datetime | None:
    """把 `extra_data["queued_at"]` 解析成 naive UTC。

    与 `app.worker.tasks._parse_cancellation_requested_at` 同口径：库里所有时间列
    都是 naive UTC，外部传进来的可能是带偏移的字符串，统一去掉 tzinfo。
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def queue_anchor(task: Task) -> datetime | None:
    """返回任务的排队起点；返回 None 表示「无法判断，本轮跳过」。"""
    extra_data = task.extra_data if isinstance(task.extra_data, dict) else {}
    parsed = _parse_anchor(extra_data.get(QUEUED_ANCHOR_KEY))
    if parsed is not None:
        return parsed
    # 历史任务没有 queued_at：用最后一次状态变更时间代替（见模块 docstring）。
    updated_at = getattr(task, "updated_at", None)
    return updated_at if isinstance(updated_at, datetime) else None


def _timeout_message(timeout_seconds: int) -> str:
    hours = timeout_seconds / 3600
    if hours >= 1 and abs(hours - round(hours)) < 1e-9:
        window = f"{int(round(hours))} 小时"
    else:
        window = f"{int(timeout_seconds)} 秒"
    return (
        f"任务排队超过 {window} 仍未获得调度，已判定为超时。"
        "请检查算力队列状态，或稍后重新提交。"
    )


async def expire_timed_out_queue_entries(
    db: AsyncSession,
    *,
    timeout_seconds: int | None = None,
    batch_size: int | None = None,
    now: datetime | None = None,
) -> int:
    """把排队超时的任务置为 `TIMEOUT`，返回本轮处理条数。

    按 `updated_at` 升序取（最早入队的先处理），每轮最多 `batch_size` 条；
    `with_for_update(skip_locked=True)` 让多副本同时跑也不会重复处理同一行
    （SQLite 下该子句被忽略，但本巡检是幂等的：已转 `TIMEOUT` 的行不再满足
    `status == QUEUED` 的筛选条件）。
    """
    window = (
        int(timeout_seconds)
        if timeout_seconds is not None
        else int(settings.TASK_QUEUE_TIMEOUT_SECONDS)
    )
    limit = (
        int(batch_size)
        if batch_size is not None
        else int(settings.TASK_QUEUE_TIMEOUT_SCAN_BATCH_SIZE)
    )
    if window <= 0 or limit <= 0:
        return 0

    moment = now or utcnow()
    cutoff = moment - timedelta(seconds=window)
    expired_tasks: list[Task] = []

    result = await db.execute(
        select(Task)
        .where(Task.status == TaskStatus.QUEUED.value)
        .order_by(Task.updated_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    for task in result.scalars().all():
        anchor = queue_anchor(task)
        if anchor is None or anchor > cutoff:
            continue
        TaskStateMachine.mark_timeout(
            task,
            error_message=_timeout_message(window),
            progress_message="排队超时",
        )
        db.add(
            TaskLog(
                task_id=task.id,
                level=QUEUED_TIMEOUT_LOG_LEVEL,
                message=_timeout_message(window),
            )
        )
        # 排队中的任务可能已持有 dispatch reservation（准入通过、消息还没被消费），
        # 转终态后必须归还，否则这份租约会一直占着配额到 stale 回收为止。
        await release_task_resource_reservation(task, reason="task_queue_timeout")
        expired_tasks.append(task)

    _publish_status_change(expired_tasks)
    return len(expired_tasks)


def _publish_status_change(tasks: list[Task]) -> None:
    """通知 SSE 订阅方立刻回读（数据库仍是唯一真值，这里只是提前叫醒）。"""
    if not tasks:
        return
    try:
        from app.services.task_event_hub import get_task_event_hub

        hub = get_task_event_hub()
    except Exception:  # noqa: BLE001 - 广播失败不影响超时判定
        return
    for task in tasks:
        hub.publish(
            str(task.id),
            {"type": "status", "taskId": str(task.id), "payload": {}},
        )


async def run_queue_timeout_sweep_once() -> int:
    """跑一轮巡检（供主循环与手动运维调用）。"""
    from app.database.session import async_session_factory

    async with async_session_factory() as db:
        expired = await expire_timed_out_queue_entries(db)
        await db.commit()
        return expired


class QueueTimeoutSweepLoop:
    """周期性排队超时巡检（与 `UploadSessionSweepLoop` 同构）。"""

    def __init__(self, *, sweep, interval_seconds: float) -> None:
        self._sweep = sweep
        self._interval_seconds = max(float(interval_seconds), 1.0)
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._run(), name="queue-timeout-sweep-loop"
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self._sweep()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 单轮失败不能让循环退出
                logger.exception("排队超时巡检单轮执行失败")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._interval_seconds
                )
            except (asyncio.TimeoutError, TimeoutError):
                continue


def build_queue_timeout_sweep_loop() -> QueueTimeoutSweepLoop | None:
    """按配置构造巡检循环；关闭时返回 `None`，`main.py` 据此跳过启停。"""
    if not settings.TASK_QUEUE_TIMEOUT_ENABLED:
        return None
    return QueueTimeoutSweepLoop(
        sweep=run_queue_timeout_sweep_once,
        interval_seconds=settings.TASK_QUEUE_TIMEOUT_SCAN_INTERVAL_SECONDS,
    )


queue_timeout_sweep_loop = build_queue_timeout_sweep_loop()


__all__ = [
    "QUEUED_ANCHOR_KEY",
    "QueueTimeoutSweepLoop",
    "build_queue_timeout_sweep_loop",
    "expire_timed_out_queue_entries",
    "queue_anchor",
    "queue_timeout_sweep_loop",
    "run_queue_timeout_sweep_once",
]
