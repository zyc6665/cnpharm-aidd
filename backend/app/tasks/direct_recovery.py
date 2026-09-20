"""Direct 模式 ssh_job 结果恢复。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from sqlalchemy import and_, or_, outerjoin, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.config import settings
from app.database.base import utcnow
from app.database.session import async_session_factory
from app.models.tasks import Task, TaskLog, TaskOutput, TaskStatus
from app.models.tools import ToolType
from app.services.standard_artifacts import (
    StandardArtifactPersistenceError,
    attach_standard_artifact_summary,
    persist_standard_artifacts_from_task_output,
)
from app.services.workflow_reconciliation import reconcile_waiting_workflow_runs
from app.tasks.executor import SSHJobExecutor, TaskExecutionError
from app.tasks.legacy_standardization import append_legacy_standard_result
from app.tasks.molecule_scoring import append_molecule_scoring_artifacts
from app.tasks.direct_runner import direct_task_runner
from app.tasks.service import create_and_schedule_tool_task
from app.tasks.state_machine import TaskStateMachine
from app.tasks.output import prepare_task_output

logger = logging.getLogger(__name__)

SHUTDOWN_CANCEL_MESSAGE = "开发模式 direct 任务已取消"
RECOVERED_SUCCESS_MESSAGE = "任务执行成功（远端结果自动补回）"
RECOVERED_FAILURE_MESSAGE = "任务执行失败（远端结果自动补回）"


def _is_workflow_node_task(task: Task) -> bool:
    params = (task.inputs.params or {}) if task.inputs else {}
    return bool(params.get("workflow_run_id") and params.get("workflow_node_id"))


async def reconcile_orphaned_direct_tasks(db: AsyncSession) -> int:
    """扫描并补回热重载后遗留的 direct ssh_job 任务。"""
    stmt = (
        select(Task)
        .options(
            joinedload(Task.tool_version),
            joinedload(Task.outputs),
            selectinload(Task.inputs),
        )
        .select_from(outerjoin(Task, TaskOutput, TaskOutput.task_id == Task.id))
        .where(TaskOutput.id.is_(None))
        .where(
            or_(
                Task.status == TaskStatus.RUNNING.value,
                and_(
                    Task.status == TaskStatus.CANCELED.value,
                    Task.progress_message == SHUTDOWN_CANCEL_MESSAGE,
                ),
            )
        )
    )

    result = await db.execute(stmt)
    tasks = result.unique().scalars().all()
    recovered_count = 0
    recovered_workflow_task = False

    for task in tasks:
        tool_version = task.tool_version
        config = tool_version.config if tool_version else {}
        if not isinstance(config, dict) or config.get("type") != ToolType.SSH_JOB.value:
            continue
        if task.status == TaskStatus.RUNNING.value and direct_task_runner.is_task_active(str(task.id)):
            continue

        executor = SSHJobExecutor(task, tool_version)
        try:
            output_result = await executor.recover_remote_result()
        except TaskExecutionError:
            logger.exception("Failed to reconcile direct ssh_job task %s", task.id)
            continue

        if not output_result:
            continue

        task_id = str(task.id)
        is_workflow_task = _is_workflow_node_task(task)

        try:
            output_result = await append_molecule_scoring_artifacts(
                db,
                task,
                tool_version,
                output_result,
            )
        except Exception as exc:
            logger.warning(
                "Recovered task %s molecule scoring failed, keeping original result: %s",
                task.id,
                exc,
            )
        try:
            output_result = await append_legacy_standard_result(
                db,
                task=task,
                tool_version_config=tool_version.config,
                output_result=output_result,
                output_file_ids=prepare_task_output(output_result)["file_ids"],
            )

            prepared_output = prepare_task_output(output_result)
            standard_persistence = await persist_standard_artifacts_from_task_output(
                db,
                task=task,
                tool_version_config=tool_version.config,
                output_result=output_result,
                output_file_ids=prepared_output["file_ids"],
            )
        except StandardArtifactPersistenceError as exc:
            await db.rollback()
            recovered_task = await db.get(Task, task_id)
            if recovered_task is None:
                continue
            TaskStateMachine.complete(
                recovered_task,
                success=False,
                error_message=str(exc),
                progress_message=RECOVERED_FAILURE_MESSAGE,
            )
            db.add(
                TaskLog(
                    task_id=task_id,
                    level="ERROR",
                    message=f"标准 result.v2 不合规，远端结果补回失败: {exc}",
                )
            )
            await db.commit()
            recovered_count += 1
            recovered_workflow_task = recovered_workflow_task or is_workflow_task
            continue
        if standard_persistence is not None:
            prepared_output["result"] = attach_standard_artifact_summary(
                prepared_output["result"],
                standard_persistence,
            )
        task_output = task.outputs or TaskOutput(task_id=task.id)
        task_output.result = prepared_output["result"]
        task_output.file_ids = prepared_output["file_ids"]
        task_output.output_type = prepared_output["output_type"]
        db.add(task_output)

        remote_result = output_result.get("result", {}) if isinstance(output_result, dict) else {}
        remote_success = bool(remote_result.get("success", True))
        duration = None
        metrics = remote_result.get("metrics")
        if isinstance(metrics, dict) and isinstance(metrics.get("duration_sec"), (int, float)):
            duration = float(metrics["duration_sec"])

        task.finished_at = (
            task.started_at + timedelta(seconds=duration)
            if duration is not None and task.started_at
            else utcnow()
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
        else:
            TaskStateMachine.complete(
                task,
                success=False,
                error_message=remote_result.get("message") or "SSH job reported failure",
                progress_message=RECOVERED_FAILURE_MESSAGE,
            )

        db.add(
            TaskLog(
                task_id=task.id,
                level="INFO",
                message=(
                    "从远端 output 目录自动补回任务结果"
                    if remote_success
                    else "从远端 output 目录自动补回失败结果"
                ),
            )
        )
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
            logger.exception("Failed to reconcile workflow runs after direct task recovery")

    return recovered_count


async def reconcile_all_orphaned_direct_tasks() -> int:
    async with async_session_factory() as session:
        return await reconcile_orphaned_direct_tasks(session)


class DirectTaskRecoveryLoop:
    """周期性恢复已脱离当前进程但仍在远端执行的 direct ssh_job 任务。"""

    def __init__(
        self,
        *,
        reconcile: Callable[[], Awaitable[object]],
        interval_seconds: float = 10.0,
    ) -> None:
        self._reconcile = reconcile
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="direct-task-recovery-loop")

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
                logger.exception("Direct task recovery loop failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                continue


direct_task_recovery_loop = DirectTaskRecoveryLoop(
    reconcile=reconcile_all_orphaned_direct_tasks,
)
