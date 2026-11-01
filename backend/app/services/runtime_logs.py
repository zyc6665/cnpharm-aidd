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
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.execution.records import task_external_execution_id
from app.models.tasks import TaskLog

logger = logging.getLogger(__name__)

#: task_logs.log_data["source"] 的取值，用于区分「平台状态行」与「容器输出」。
RUNTIME_LOG_SOURCE = "runtime"

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
    """该任务是否已经归档过容器日志。"""
    statement = (
        select(func.count())
        .select_from(TaskLog)
        .where(
            TaskLog.task_id == task_id,
            TaskLog.log_data["source"].as_string() == RUNTIME_LOG_SOURCE,
        )
    )
    return bool((await db.execute(statement)).scalar())


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
) -> tuple[str, bool]:
    """按游标把日志拉完，返回（内容, 是否被截断）。"""
    pieces: list[str] = []
    total = 0
    cursor: str | None = None
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

    execution_id = task_external_execution_id(task)
    if not execution_id:
        # 内置/直跑任务没有外部执行句柄，日志由执行器自己写，无需归档。
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
        )
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
    "already_harvested",
    "harvest_task_runtime_logs",
    "split_log_content",
]
