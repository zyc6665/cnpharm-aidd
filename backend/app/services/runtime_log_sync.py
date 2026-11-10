"""运行中任务的容器日志与进度同步。

为什么需要这一层
----------------
执行侧（K8s Job）在跑长任务时会往 stdout 打进度标记：

```
__DRP_PROGRESS__ {"pct": 45, "message": "阶段 3/7：水化体系"}
```

但平台此前只把容器日志在**终态**抓一次归档（见 ``app.services.runtime_logs``），
运行期既不读日志也不解析进度。于是 3600 秒的 MD 任务在详情页上只有「运行中」
三个字：用户看不到任何进展，也判断不了它是慢还是挂了（docs/26 H-2、H-3）。

这一层做两件事，都发生在任务**运行中**：

1. **增量拉日志**：按游标（上一行的时间戳）用 ``sinceTime`` 拉取新增部分，追加写进
   ``task_logs``（``log_data.source="runtime"``、``log_data.stream="live"``），
   于是既有的 ``GET /tasks/{id}/logs`` 与 SSE ``log`` 帧不用改就能显示出来。
2. **解析进度标记**：把最后一条 ``__DRP_PROGRESS__`` 折算成
   ``task.progress`` / ``task.progress_message``，SSE ``progress`` 帧随之生效。

三条约定
--------
- **只前进**：进度取 ``max(已有, 新值)``。模型打印的百分比偶尔会回退（多阶段重跑），
  进度条倒退比不动更让人怀疑任务在重来。
- **幂等**：游标存在 ``task.extra_data["runtimeLog"].cursor``，重复同步不会重复写行；
  没有新内容时直接跳过，不产生空日志。
- **尽力而为**：单个任务失败只记 warning 并跳过，绝不影响其它任务，也不改任务状态。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.execution.records import task_execution_record_external_id
from app.models.tasks import Task, TaskLog, TaskStatus
from app.services.runtime_logs import (
    RUNTIME_LOG_SOURCE,
    RUNTIME_LOG_STREAM_LIVE,
    external_execution_id_from_extra,
    last_log_timestamp,
    resolve_adapter_type,
    split_log_content,
    strip_log_timestamps,
)

logger = logging.getLogger(__name__)

#: 执行侧打印进度标记用的前缀（见 deploy/model-images/k8s/gromacs/gromacs_platform.py）。
PROGRESS_MARKER = "__DRP_PROGRESS__"

#: 游标与已有行数的存放位置（``task.extra_data`` 内的键）。
RUNTIME_LOG_META_KEY = "runtimeLog"

#: 只有这些状态需要同步：排队与终态都不需要拉运行日志。
SYNCABLE_STATUSES = {TaskStatus.RUNNING.value}

#: 单轮单任务最多写多少字符，防止一个刷屏模型把一轮同步拖成分钟级。
DEFAULT_MAX_CHARS = 200_000

_PROGRESS_PAYLOAD = re.compile(r"\{.*\}")


def parse_progress_marker(content: str) -> dict[str, Any] | None:
    """取内容里**最后一条**进度标记，返回 ``{"pct": float, "message": str|None}``。

    多个标记取最后一条：同一批日志里前面的是历史进度，写进去只会让进度条倒退。
    """
    if not content or PROGRESS_MARKER not in content:
        return None
    latest: dict[str, Any] | None = None
    for line in content.splitlines():
        index = line.find(PROGRESS_MARKER)
        if index < 0:
            continue
        payload_text = line[index + len(PROGRESS_MARKER) :].strip()
        match = _PROGRESS_PAYLOAD.search(payload_text)
        if match is None:
            # 只有前缀没有 JSON：可能是被截断的半行，忽略而不是猜。
            continue
        try:
            payload = json.loads(match.group(0))
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        pct = _coerce_pct(payload.get("pct"))
        if pct is None:
            continue
        message = payload.get("message")
        latest = {
            "pct": pct,
            "message": str(message).strip() if isinstance(message, str) else None,
        }
    return latest


def _coerce_pct(value: Any) -> float | None:
    """把 ``pct`` 归一到 0~100；越界一律丢弃（宁可不动，也不显示 200%）。"""
    if isinstance(value, bool):
        return None
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return None
    if pct != pct:  # NaN
        return None
    if pct < 0 or pct > 100:
        return None
    return round(pct, 2)


def _meta(task: Task) -> dict[str, Any]:
    extra = task.extra_data if isinstance(task.extra_data, dict) else {}
    meta = extra.get(RUNTIME_LOG_META_KEY)
    return dict(meta) if isinstance(meta, dict) else {}


def _set_meta(task: Task, meta: dict[str, Any]) -> None:
    extra = dict(task.extra_data) if isinstance(task.extra_data, dict) else {}
    extra[RUNTIME_LOG_META_KEY] = meta
    task.extra_data = extra


async def sync_task_runtime_logs(
    db: AsyncSession,
    *,
    task: Task,
    execution_service: Any | None = None,
    max_chars: int | None = None,
) -> dict[str, Any]:
    """把运行中任务的新增日志与进度同步一次，返回本轮结果摘要。"""
    summary: dict[str, Any] = {"taskId": str(task.id), "lines": 0, "progress": None}

    execution_id = await task_execution_record_external_id(db, task=task)
    if not execution_id:
        execution_id = external_execution_id_from_extra(task)
    if not execution_id:
        summary["skipped"] = "没有外部执行句柄"
        return summary

    if execution_service is None:
        from app.execution.runtime import get_execution_service

        execution_service = get_execution_service()

    meta = _meta(task)
    cursor = meta.get("cursor") if isinstance(meta.get("cursor"), str) else None
    adapter_type = await resolve_adapter_type(db, task=task)

    chunk = await execution_service.logs(adapter_type, execution_id, cursor)
    content = getattr(chunk, "content", "") or ""
    if not content.strip():
        return summary

    limit = max_chars or int(getattr(settings, "TASK_RUNTIME_LOG_SYNC_MAX_CHARS", DEFAULT_MAX_CHARS))
    if len(content) > limit:
        # 只保留尾部：进度标记总是最新的那几行，前面的历史在终态归档里补。
        content = content[-limit:]

    progress = parse_progress_marker(content)
    if progress is not None:
        summary["progress"] = progress["pct"]
        _apply_progress(task, progress)

    body = strip_log_timestamps(content)
    for index, piece in enumerate(split_log_content(body)):
        db.add(
            TaskLog(
                task_id=str(task.id),
                level="INFO",
                message=piece,
                log_data={
                    "source": RUNTIME_LOG_SOURCE,
                    "stream": RUNTIME_LOG_STREAM_LIVE,
                    "sequence": index,
                    "adapter_type": adapter_type,
                    "external_id": execution_id,
                },
            )
        )
        summary["lines"] += 1

    new_cursor = last_log_timestamp(content) or getattr(chunk, "next_cursor", None)
    if new_cursor:
        meta["cursor"] = new_cursor
    meta["updatedAt"] = datetime.now(timezone.utc).isoformat()
    _set_meta(task, meta)
    await db.flush()
    return summary


def _apply_progress(task: Task, progress: dict[str, Any]) -> None:
    """只前进不后退；进度到 100 保留，由状态机在成功时收尾。"""
    current = float(task.progress or 0.0)
    pct = float(progress["pct"])
    if pct > current:
        task.progress = pct
    message = progress.get("message")
    if message and message != task.progress_message:
        task.progress_message = message[:500]


async def run_runtime_log_sync_once(
    *,
    execution_service: Any | None = None,
    max_tasks: int | None = None,
) -> int:
    """扫一遍运行中任务并逐个同步，返回成功同步的任务数。"""
    from app.database import async_session_factory

    limit = max_tasks or int(getattr(settings, "TASK_RUNTIME_LOG_SYNC_MAX_TASKS", 50))
    synced = 0
    async with async_session_factory() as db:
        result = await db.execute(
            select(Task)
            .where(Task.status == TaskStatus.RUNNING.value)
            .order_by(Task.updated_at.asc())
            .limit(max(limit, 1))
        )
        tasks = list(result.scalars().all())
        for task in tasks:
            try:
                summary = await sync_task_runtime_logs(
                    db, task=task, execution_service=execution_service
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 单任务失败不能停下整轮
                logger.warning("任务 %s 运行期日志同步失败：%s", task.id, exc)
                await db.rollback()
                continue
            if summary.get("lines") or summary.get("progress") is not None:
                synced += 1
        await db.commit()
    return synced


class RuntimeLogSyncLoop:
    """周期性运行期日志/进度同步（与 ``QueueTimeoutSweepLoop`` 同构）。"""

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
        self._task = asyncio.create_task(self._run(), name="runtime-log-sync-loop")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        # 退出条件写在 while 上而不是只靠 cancel()：stop() 先 set 再 cancel，
        # 事件置位后 wait_for 立刻返回，纯计算的循环体会让 CancelledError
        # 拿不到投递窗口（docs/17 §5.11.1 记过这个挂死）。
        while not self._stop_event.is_set():
            try:
                await self._sweep()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 单轮失败不能让循环退出
                logger.exception("运行期日志同步单轮执行失败")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._interval_seconds
                )
            except (asyncio.TimeoutError, TimeoutError):
                continue


def build_runtime_log_sync_loop() -> RuntimeLogSyncLoop | None:
    """按配置构造同步循环；关闭时返回 ``None``，``main.py`` 据此跳过启停。"""
    if not getattr(settings, "TASK_RUNTIME_LOG_SYNC_ENABLED", True):
        return None
    return RuntimeLogSyncLoop(
        sweep=run_runtime_log_sync_once,
        interval_seconds=float(
            getattr(settings, "TASK_RUNTIME_LOG_SYNC_INTERVAL_SECONDS", 10.0)
        ),
    )


runtime_log_sync_loop = build_runtime_log_sync_loop()


__all__ = [
    "PROGRESS_MARKER",
    "RUNTIME_LOG_META_KEY",
    "RuntimeLogSyncLoop",
    "build_runtime_log_sync_loop",
    "parse_progress_marker",
    "run_runtime_log_sync_once",
    "runtime_log_sync_loop",
    "sync_task_runtime_logs",
]
