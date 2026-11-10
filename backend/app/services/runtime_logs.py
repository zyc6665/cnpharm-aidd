"""把容器运行时日志归档到 ``task_logs``。

为什么需要这一层
----------------
K8s Job 的 ``ttlSecondsAfterFinished`` 到期时会把 Job 连同 Pod 一起删掉，
Pod 一删，``read_namespaced_pod_log`` 就永久 404。而平台此前**没有任何地方**
落过容器日志：``ExecutionService.logs`` 只被适配器链路引用，``GET /tasks/{id}/logs``
也只读 ``task_logs`` 表（里面只有平台自己写的状态行）。结果是「日志能看但会过期
消失」，与 G-3 的「可回放」要求冲突。

因此任务进终态时抓一次容器日志、写进 ``task_logs``，让读日志不再依赖 Pod 是否
还活着，Job 的保留时长也就能按排障需要调短。

三条约定
--------
- **尽力而为**：任何异常都只记 warning，绝不影响任务本身的终态写入。
- **幂等**：同一任务只归档一次（以 ``log_data.source == "runtime"`` 为标记），
  重试/重复调用直接返回 0。
- **有上限**：单任务最多保存 ``TASK_LOG_MAX_BYTES``，超出部分截断并在最后一行
  标注，避免一个刷屏的模型把任务日志表撑爆。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.execution.records import (
    task_execution_record_external_id,
    task_external_execution_id,
)
from app.models.tasks import TaskLog

logger = logging.getLogger(__name__)

#: 适配器按 ``timestamps=true`` 拉日志时，每行前缀是 RFC3339 时间戳。
#: 入库前要剥掉——``task_logs.timestamp`` 才是权威时间，留着会让页面上
#: 时间显示两遍（一次来自列，一次来自正文）。
TIMESTAMPED_LOG_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}T[\d:.]+Z)\s")


def strip_log_timestamps(content: str) -> str:
    """去掉每行行首的容器时间戳（保留原有换行，不重新拼行）。"""
    lines: list[str] = []
    for line in content.splitlines(keepends=True):
        match = TIMESTAMPED_LOG_LINE.match(line)
        lines.append(line[match.end() :] if match else line)
    return "".join(lines)


def last_log_timestamp(content: str) -> str | None:
    """取最后一行的时间戳，作为下一次增量拉取的游标。"""
    for line in reversed(content.splitlines()):
        if not line.strip():
            continue
        match = TIMESTAMPED_LOG_LINE.match(line)
        return match.group(1) if match else None
    return None

#: task_logs.log_data["source"] 的取值，用于区分「平台状态行」与「容器输出」。
RUNTIME_LOG_SOURCE = "runtime"

#: task_logs.log_data["stream"] 的取值。``live`` 是运行中的增量同步
#: （``app.services.runtime_log_sync``），``final`` 是终态的一次性归档。
#: 分开记录是必要的：``already_harvested`` 只认 ``final``，否则运行期同步过
#: 一轮之后，终态归档会以为自己已经做过而漏掉任务结尾的日志。
RUNTIME_LOG_STREAM_LIVE = "live"
RUNTIME_LOG_STREAM_FINAL = "final"

#: 没有执行记录时假定的适配器类型。K8s Job 是唯一会随 TTL 消失的承载方式。
DEFAULT_ADAPTER_TYPE = "k8s_job"

#: 单行 message 的字符上限。日志一次抓下来可能是几百 KB，整块塞进一行的
#: Text 列会让「按页翻日志」失去意义，也更容易撞数据库的字段上限。
MAX_MESSAGE_CHARS = 8192


def _truncate_utf8(content: str, max_bytes: int) -> tuple[str, bool]:
    """按 UTF-8 字节上限截断，并且不切断多字节字符。"""
    encoded = content.encode("utf-8")
    if len(encoded) <= max_bytes:
        return content, False
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True


def split_log_content(content: str) -> list[str]:
    """把一整段日志切成若干块，优先在换行处断开。

    模型输出经常是「一行几万个字符」的进度条或 JSON，所以必须在没有换行时
    也能硬切，否则单行会超限。
    """
    if not content:
        return []
    chunks: list[str] = []
    remaining = content
    while len(remaining) > MAX_MESSAGE_CHARS:
        window = remaining[:MAX_MESSAGE_CHARS]
        cut = window.rfind("\n")
        # 换行点太靠前时宁可硬切：留太少会切出大量碎片行。
        if cut < MAX_MESSAGE_CHARS // 2:
            cut = len(window)
        else:
            cut += 1
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        chunks.append(remaining)
    return chunks


async def already_harvested(db: AsyncSession, *, task_id: str) -> bool:
    """该任务是否已经做过终态归档。"""
    statement = (
        select(func.count())
        .select_from(TaskLog)
        .where(
            TaskLog.task_id == task_id,
            TaskLog.log_data["source"].as_string() == RUNTIME_LOG_SOURCE,
            TaskLog.log_data["stream"].as_string() == RUNTIME_LOG_STREAM_FINAL,
        )
    )
    return bool((await db.execute(statement)).scalar())


async def resolve_adapter_type(db: AsyncSession, *, task: Any) -> str:
    """取当前 attempt 的执行适配器类型，取不到就按 K8s Job 处理。"""
    return await _resolve_adapter_type(db, task=task)


def external_execution_id_from_extra(task: Any) -> str | None:
    """从 ``task.extra_data`` 里读外部执行句柄。

    键名沿用 ``task_external_execution_id`` 的 ``external_id``/``remote_run_id``，
    另外兼容早期写在 ``externalExecutionId`` 的历史数据——三个键指的是同一件事，
    多一个名字就多一处读不到。
    """
    extra = getattr(task, "extra_data", None)
    if not isinstance(extra, dict):
        return None
    for key in ("external_id", "remote_run_id", "externalExecutionId", "external_execution_id"):
        value = extra.get(key)
        if value:
            return str(value)
    return None


def runtime_log_cursor(task: Any) -> str | None:
    """读运行期同步存下的日志游标（``task.extra_data["runtimeLog"]["cursor"]``）。

    与 ``runtime_log_sync.RUNTIME_LOG_META_KEY`` 同源；这里不 import 那边的常量，
    是为了让 ``runtime_logs`` 保持零依赖——它被 ``runtime_log_sync`` 反向引用。
    """
    extra = getattr(task, "extra_data", None)
    if not isinstance(extra, dict):
        return None
    meta = extra.get("runtimeLog")
    if not isinstance(meta, dict):
        return None
    cursor = meta.get("cursor")
    return cursor if isinstance(cursor, str) and cursor else None


async def _resolve_adapter_type(db: AsyncSession, *, task: Any) -> str:
    """从当前 attempt 的执行记录里取适配器类型，取不到就按 K8s Job 处理。"""
    from app.execution.records import task_execution_record_id

    record_id = task_execution_record_id(task)
    if not record_id:
        return DEFAULT_ADAPTER_TYPE
    try:
        from app.models.executions import ExecutionRecord

        record = await db.get(ExecutionRecord, record_id)
    except Exception:  # pragma: no cover - 记录表不可用时退回默认值
        return DEFAULT_ADAPTER_TYPE
    adapter_type = str(getattr(record, "adapter_type", "") or "").strip()
    return adapter_type or DEFAULT_ADAPTER_TYPE


async def _collect_content(
    service: Any,
    *,
    adapter_type: str,
    execution_id: str,
    max_bytes: int,
    cursor: str | None = None,
) -> tuple[str, bool]:
    """按游标把日志拉完，返回（内容, 是否被截断）。

    ``cursor`` 是**上一个游标**：运行期同步（``runtime_log_sync``）已经写进
    ``task_logs`` 的部分不要再拉一遍，否则终态归档会把同一段日志第二次写进日志表，
    用户在页面上看到每行都重复。传 ``None`` 表示从头拉（例如运行期同步没跑过）。
    """
    pieces: list[str] = []
    total = 0
    while True:
        chunk = await service.logs(adapter_type, execution_id, cursor)
        content = getattr(chunk, "content", "") or ""
        if content:
            total += len(content.encode("utf-8"))
            pieces.append(content)
            if total >= max_bytes:
                joined, _ = _truncate_utf8("".join(pieces), max_bytes)
                return joined, True
        next_cursor = getattr(chunk, "next_cursor", None)
        if getattr(chunk, "complete", False) or not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    return "".join(pieces), False


async def harvest_task_runtime_logs(
    db: AsyncSession,
    *,
    task: Any,
    execution_service: Any | None = None,
    max_bytes: int | None = None,
) -> int:
    """把任务当前 attempt 的容器日志写进 ``task_logs``，返回写入行数。

    归档失败不影响任务终态：所有异常在这里被吞掉，只留一条 warning。
    """
    if not getattr(settings, "TASK_LOG_HARVEST_ENABLED", True):
        return 0

    task_id = str(getattr(task, "id", "") or "")
    if not task_id:
        return 0

    execution_id = task_external_execution_id(task) or external_execution_id_from_extra(task)
    if not execution_id:
        # k8s/ssh 这类托管执行器把句柄写在 ExecutionRecord 上，任务元数据里没有。
        # 只查 extra_data 会一直取到 None，归档于是静默不生效（曾真实发生）。
        execution_id = await task_execution_record_external_id(db, task=task)
    if not execution_id:
        # 内置/直跑任务确实没有外部执行句柄，日志由执行器自己写，无需归档。
        return 0

    try:
        if await already_harvested(db, task_id=task_id):
            return 0

        if execution_service is None:
            from app.execution.runtime import get_execution_service

            execution_service = get_execution_service()

        adapter_type = await _resolve_adapter_type(db, task=task)
        limit = max_bytes or int(getattr(settings, "TASK_LOG_MAX_BYTES", 2_000_000))
        content, truncated = await _collect_content(
            execution_service,
            adapter_type=adapter_type,
            execution_id=execution_id,
            max_bytes=max(limit, 1),
            # 接上运行期同步的游标：那一部分已经写进日志表，再拉一遍会让用户
            # 看到每行都重复（真实缺陷，曾因为没有 live/final 之分而出现）。
            cursor=runtime_log_cursor(task),
        )
        if not content.strip():
            return 0

        # 与运行期同步保持同一种正文形态：时间戳由 task_logs.timestamp 承担。
        content = strip_log_timestamps(content)
        if not content.strip():
            return 0

        chunks = split_log_content(content)
        rows = 0
        for index, chunk in enumerate(chunks):
            is_last = index == len(chunks) - 1
            db.add(
                TaskLog(
                    task_id=task_id,
                    level="INFO",
                    message=chunk,
                    log_data={
                        "source": RUNTIME_LOG_SOURCE,
                        "stream": RUNTIME_LOG_STREAM_FINAL,
                        "sequence": index,
                        "adapter_type": adapter_type,
                        "external_id": execution_id,
                        "truncated": bool(truncated and is_last),
                    },
                )
            )
            rows += 1
        await db.flush()
        logger.info(
            "任务 %s 的容器日志已归档：%s 行 / %s 字节%s",
            task_id,
            rows,
            len(content.encode("utf-8")),
            "（已截断）" if truncated else "",
        )
        return rows
    except Exception as exc:  # noqa: BLE001 - 归档失败不能影响任务终态
        logger.warning("任务 %s 的容器日志归档失败（不影响任务结果）：%s", task_id, exc)
        return 0


__all__ = [
    "MAX_MESSAGE_CHARS",
    "RUNTIME_LOG_SOURCE",
    "RUNTIME_LOG_STREAM_FINAL",
    "RUNTIME_LOG_STREAM_LIVE",
    "already_harvested",
    "external_execution_id_from_extra",
    "harvest_task_runtime_logs",
    "last_log_timestamp",
    "resolve_adapter_type",
    "runtime_log_cursor",
    "split_log_content",
    "strip_log_timestamps",
]
