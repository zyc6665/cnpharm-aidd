"""Recovery loop for remote-tool.v1 tasks after worker interruption."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.common.time import utcnow
from app.config import settings
from app.database.session import async_session_factory
from app.execution.records import finish_task_execution_record_best_effort
from app.models.executions import ExecutionRecord
from app.models.tasks import Task, TaskLog, TaskOutput, TaskStatus
from app.models.tools import ToolVersion
from app.services.standard_artifacts import StandardArtifactPersistenceError
from app.services.workflow_reconciliation import reconcile_waiting_workflow_runs
from app.tasks.executors.errors import TaskExecutionError
from app.tasks.executors.remote_api import RemoteAPIExecutor
from app.tasks.recovery import is_workflow_node_task, prepare_recovered_task_output
from app.tasks.service import create_and_schedule_tool_task
from app.tasks.state_machine import TaskStateMachine

logger = logging.getLogger(__name__)

RECOVERED_SUCCESS_MESSAGE = "任务执行成功（Remote API 结果自动补回）"
RECOVERED_FAILURE_MESSAGE = "任务执行失败（Remote API 结果自动补回）"
REMOTE_RECOVERY_FAILURES_KEY = "remote_recovery_failures"
REMOTE_RECOVERY_NEXT_ATTEMPT_KEY = "remote_recovery_next_attempt_at"
REMOTE_RECOVERY_LAST_ERROR_KEY = "remote_recovery_last_error"
REMOTE_RECOVERY_ALERTED_KEY = "remote_recovery_alerted"


async def reconcile_orphaned_remote_tasks(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    stale_after: timedelta = timedelta(minutes=5),
    batch_size: int = 20,
) -> int:
    """Inspect stale remote runs and materialize terminal results once."""
    current_time = now or utcnow()
    cutoff = current_time - stale_after
    next_attempt_expression = Task.extra_data[REMOTE_RECOVERY_NEXT_ATTEMPT_KEY].as_string()
    remote_type_filter = Task.tool_version.has(
        (ToolVersion.config["type"].as_string() == "remote_api")
        & (ToolVersion.config["mode"].as_string() == "remote_tool_v1")
    )
    stmt = (
        select(Task, ExecutionRecord)
        .join(
            ExecutionRecord,
            ExecutionRecord.request_snapshot["task_id"].as_string() == Task.id,
        )
        .options(
            joinedload(Task.tool_version),
            joinedload(Task.outputs),
            selectinload(Task.inputs),
        )
        .where(
            Task.status == TaskStatus.RUNNING.value,
            remote_type_filter,
            ExecutionRecord.status == "running",
            ExecutionRecord.adapter_type == "remote_job",
            ExecutionRecord.updated_at <= cutoff,
            or_(
                ExecutionRecord.external_id.is_not(None),
                Task.extra_data["remote_run_id"].as_string().is_not(None),
            ),
            or_(
                next_attempt_expression.is_(None),
                next_attempt_expression <= current_time.isoformat(),
            ),
        )
        .order_by(ExecutionRecord.updated_at.asc(), ExecutionRecord.id.asc())
        .with_for_update(skip_locked=True)
        .limit(batch_size)
    )
    result = await db.execute(stmt)
    rows = result.unique().all()
    recovered_count = 0
    recovered_workflow_task = False

    for task, record in rows:
        if not _remote_recovery_retry_due(task, current_time):
            continue

        tool_version = task.tool_version
        if tool_version is None or task.outputs is not None:
            continue

        remote_run_id = str(record.external_id or "").strip()
        if not remote_run_id:
            remote_run_id = str((task.extra_data or {}).get("remote_run_id") or "").strip()
        if not remote_run_id:
            logger.warning("Remote task %s has no recoverable run id", task.id)
            continue

        is_workflow_task = is_workflow_node_task(task)
        executor = RemoteAPIExecutor(task, tool_version)
        try:
            output_result = await executor.recover_remote_run(remote_run_id)
        except TaskExecutionError as exc:
            await _schedule_remote_recovery_retry(
                db,
                task,
                now=current_time,
                error_message=str(exc),
            )
            continue

        if output_result.get("recovery_pending"):
            _clear_remote_recovery_failure(task)
            _apply_remote_progress(task, output_result, current_time)
            await db.commit()
            continue

        task_id = str(task.id)
        try:
            prepared_output, output_result = await prepare_recovered_task_output(
                db,
                task=task,
                tool_version=tool_version,
                output_result=output_result,
            )
        except StandardArtifactPersistenceError as exc:
            await db.rollback()
            recovered_task = await db.get(Task, task_id)
            if recovered_task is None:
                continue
            await _finish_recovered_failure(
                db,
                recovered_task,
                error_message=str(exc),
                log_message=f"标准 result.v2 不合规，Remote API 结果补回失败: {exc}",
            )
            recovered_count += 1
            recovered_workflow_task = recovered_workflow_task or is_workflow_task
            continue

        task_output = task.outputs or TaskOutput(task_id=task.id)
        task_output.result = prepared_output["result"]
        task_output.file_ids = prepared_output["file_ids"]
        task_output.output_type = prepared_output["output_type"]
        db.add(task_output)
        _clear_remote_recovery_failure(task)

        remote_result = output_result.get("result", {})
        remote_success = bool(remote_result.get("success", True))
        metrics = remote_result.get("metrics")
        duration = (
            float(metrics["duration_sec"])
            if isinstance(metrics, dict)
            and isinstance(metrics.get("duration_sec"), (int, float))
            else None
        )
        if duration is not None:
            task.execution_time_sec = int(duration)
        if remote_success:
            task.error_message = None
            TaskStateMachine.complete(
                task,
                success=True,
                progress_message=RECOVERED_SUCCESS_MESSAGE,
            )
            await finish_task_execution_record_best_effort(
                task=task,
                status="succeeded",
            )
            log_message = "从 Remote API 运行自动补回任务结果"
        else:
            error_message = remote_result.get("message") or "Remote API run reported failure"
            TaskStateMachine.complete(
                task,
                success=False,
                error_message=error_message,
                progress_message=RECOVERED_FAILURE_MESSAGE,
            )
            await finish_task_execution_record_best_effort(
                task=task,
                status="failed",
                error_message=error_message,
            )
            log_message = "从 Remote API 运行自动补回失败结果"

        db.add(TaskLog(task_id=task.id, level="INFO", message=log_message))
        await db.commit()
        recovered_count += 1
        recovered_workflow_task = recovered_workflow_task or is_workflow_task

    if recovered_workflow_task:
        try:
            await reconcile_waiting_workflow_runs(
                db,
                batch_size=settings.WORKFLOW_RECONCILE_BATCH_SIZE,
                schedule_task_fn=create_and_schedule_tool_task,
            )
        except Exception:
            logger.exception("Failed to reconcile workflow runs after remote task recovery")

    return recovered_count


def _apply_remote_progress(task: Any, output_result: dict[str, Any], now: datetime) -> None:
    status_payload = output_result.get("remote_status")
    if not isinstance(status_payload, dict):
        return
    progress = status_payload.get("progress")
    if isinstance(progress, (int, float)):
        task.progress = float(max(0, min(100, progress)))
    message = status_payload.get("message")
    if isinstance(message, str) and message.strip():
        task.progress_message = message.strip()
    task.updated_at = now


def _remote_recovery_retry_due(task: Any, now: datetime) -> bool:
    raw_next_attempt = (getattr(task, "extra_data", None) or {}).get(
        REMOTE_RECOVERY_NEXT_ATTEMPT_KEY
    )
    if not raw_next_attempt:
        return True
    try:
        return datetime.fromisoformat(str(raw_next_attempt)) <= now
    except ValueError:
        logger.warning("Remote task %s has invalid recovery backoff timestamp", task.id)
        return True


def _clear_remote_recovery_failure(task: Any) -> None:
    data = dict(getattr(task, "extra_data", None) or {})
    changed = False
    for key in (
        REMOTE_RECOVERY_FAILURES_KEY,
        REMOTE_RECOVERY_NEXT_ATTEMPT_KEY,
        REMOTE_RECOVERY_LAST_ERROR_KEY,
        REMOTE_RECOVERY_ALERTED_KEY,
    ):
        if key in data:
            data.pop(key, None)
            changed = True
    if changed:
        task.extra_data = data


async def _schedule_remote_recovery_retry(
    db: AsyncSession,
    task: Any,
    *,
    now: datetime,
    error_message: str,
) -> None:
    data = dict(getattr(task, "extra_data", None) or {})
    try:
        failures = int(data.get(REMOTE_RECOVERY_FAILURES_KEY) or 0) + 1
    except (TypeError, ValueError):
        failures = 1
    initial_backoff = max(settings.REMOTE_TASK_RECOVERY_INITIAL_BACKOFF_SECONDS, 1)
    max_backoff = max(settings.REMOTE_TASK_RECOVERY_MAX_BACKOFF_SECONDS, initial_backoff)
    backoff_seconds = min(initial_backoff * (2 ** (failures - 1)), max_backoff)
    next_attempt_at = now + timedelta(seconds=backoff_seconds)
    data.update(
        {
            REMOTE_RECOVERY_FAILURES_KEY: failures,
            REMOTE_RECOVERY_NEXT_ATTEMPT_KEY: next_attempt_at.isoformat(),
            REMOTE_RECOVERY_LAST_ERROR_KEY: error_message[:500],
        }
    )

    alert_threshold = max(settings.REMOTE_TASK_RECOVERY_ALERT_AFTER_FAILURES, 1)
    should_alert = failures >= alert_threshold and not data.get(REMOTE_RECOVERY_ALERTED_KEY)
    if should_alert:
        data[REMOTE_RECOVERY_ALERTED_KEY] = True
        db.add(
            TaskLog(
                task_id=task.id,
                level="ERROR",
                message=(
                    f"Remote API 结果恢复连续失败 {failures} 次，"
                    f"请检查远端服务: {error_message[:300]}"
                ),
            )
        )

    task.extra_data = data
    task.progress_message = (
        f"远端服务暂时不可用，第 {failures} 次恢复探测失败，"
        f"将于 {next_attempt_at.isoformat()} 重试"
    )
    task.updated_at = now
    await db.commit()
    logger.warning(
        "Remote task %s recovery deferred: failure=%s next_attempt=%s error=%s",
        task.id,
        failures,
        next_attempt_at.isoformat(),
        error_message,
    )


async def _finish_recovered_failure(
    db: AsyncSession,
    task: Any,
    *,
    error_message: str,
    log_message: str,
) -> None:
    TaskStateMachine.complete(
        task,
        success=False,
        error_message=error_message,
        progress_message=RECOVERED_FAILURE_MESSAGE,
    )
    await finish_task_execution_record_best_effort(
        task=task,
        status="failed",
        error_message=error_message,
    )
    db.add(TaskLog(task_id=task.id, level="ERROR", message=log_message))
    await db.commit()


async def reconcile_all_orphaned_remote_tasks() -> int:
    async with async_session_factory() as session:
        return await reconcile_orphaned_remote_tasks(
            session,
            stale_after=timedelta(seconds=settings.REMOTE_TASK_RECOVERY_STALE_AFTER_SECONDS),
            batch_size=settings.REMOTE_TASK_RECOVERY_BATCH_SIZE,
        )


class RemoteTaskRecoveryLoop:
    """Periodically recover remote-tool.v1 tasks in direct mode."""

    def __init__(
        self,
        *,
        reconcile: Callable[[], Awaitable[object]],
        interval_seconds: float,
    ):
        self._reconcile = reconcile
        self._interval_seconds = interval_seconds
        self._task: Any = None
        self._stop_event: Any = None

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="remote-task-recovery-loop")

    async def stop(self) -> None:
        if not self._task:
            return
        if self._stop_event:
            self._stop_event.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await self._reconcile()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Remote task recovery loop failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                continue


remote_task_recovery_loop = RemoteTaskRecoveryLoop(
    reconcile=reconcile_all_orphaned_remote_tasks,
    interval_seconds=float(settings.REMOTE_TASK_RECOVERY_INTERVAL_SECONDS),
)


__all__ = [
    "RemoteTaskRecoveryLoop",
    "reconcile_all_orphaned_remote_tasks",
    "reconcile_orphaned_remote_tasks",
    "remote_task_recovery_loop",
]
