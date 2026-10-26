"""Reusable platform task cancellation."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.config import settings, use_direct_task_execution
from app.execution.records import (
    finish_task_execution_record_best_effort,
    task_external_execution_id,
    task_execution_record_external_id,
)
from app.logging.audit import AuditAction, AuditResult, get_audit_logger
from app.models.tasks import Task, TaskStatus
from app.models.tools import ToolVersion
from app.models.users import User
from app.tasks.direct_runner import direct_task_runner as default_direct_task_runner
from app.common.task_context import task_project_id
from app.tasks.resource_lease import release_task_resource_reservation
from app.tasks.state_machine import TaskStateMachine
from app.tasks.attempts import (
    get_execution_attempt_id,
    mark_task_cancellation_requested,
)


logger = logging.getLogger(__name__)


async def cancel_platform_task(
    db: AsyncSession,
    *,
    task: Task,
    current_user: User,
    direct_runner=default_direct_task_runner,
) -> bool:
    """Cancel a pending, queued or running task through its configured execution backend."""
    if task.status not in {
        TaskStatus.PENDING.value,
        TaskStatus.QUEUED.value,
        TaskStatus.RUNNING.value,
    }:
        return False

    was_running = task.status == TaskStatus.RUNNING.value
    attempt_id = get_execution_attempt_id(task)

    # Persist the local cancellation barrier before contacting a remote
    # executor. A failed remote cancel must not leave the task RUNNING.
    if was_running:
        mark_task_cancellation_requested(
            task,
            attempt_id=attempt_id,
            reason="user_requested",
        )
    TaskStateMachine.cancel(task)

    try:
        await _cancel_remote_tool_if_needed(db, task=task)
    except Exception as exc:
        logger.warning(
            "Remote cancellation pending for task %s: %s",
            task.id,
            exc,
        )
        extra_data = dict(task.extra_data or {})
        extra_data["remote_cancel_pending"] = True
        extra_data["remote_cancel_error"] = str(exc)
        extra_data["remote_cancel_next_retry_at"] = (
            utcnow()
            + timedelta(seconds=max(int(settings.REMOTE_CANCEL_RETRY_INTERVAL_SECONDS), 1))
        ).isoformat()
        task.extra_data = extra_data

    if use_direct_task_execution():
        try:
            direct_runner.cancel_task(str(task.id))
        except Exception as exc:
            logger.warning("Direct cancellation failed for task %s: %s", task.id, exc)
    elif task.celery_task_id:
        from app.tasks.queue_manager import TaskQueueManager

        # A revoke without termination only prevents a queued message from
        # being consumed.  For a task that is already running the worker may
        # keep executing while the API has already marked the task canceled,
        # which would make a subsequent retry overlap the old attempt.  Ask
        # Celery to terminate the active child and keep a compatibility
        # fallback for lightweight test doubles / legacy integrations that
        # still expose the old one-argument signature.
        try:
            TaskQueueManager.revoke_task(
                task.celery_task_id,
                terminate=was_running,
                signal="SIGTERM",
            )
        except TypeError:
            TaskQueueManager.revoke_task(task.celery_task_id)

    if not was_running:
        # Pending reservations are safe to release immediately. A running
        # worker may still hold the lease until its executor finally block
        # exits; releasing it here could let another task overbook the worker.
        await release_task_resource_reservation(task, reason="task_canceled")
    try:
        await finish_task_execution_record_best_effort(
            task=task,
            status="cancelled",
            error_message="任务已取消",
        )
    except Exception as exc:
        logger.warning(
            "Failed to finish execution record for canceled task %s: %s",
            task.id,
            exc,
        )
    _audit_task_cancel(task=task, current_user=current_user)
    return True


def _audit_task_cancel(*, task: Task, current_user: User) -> None:
    get_audit_logger().log_task_operation(
        user_id=str(current_user.id),
        action=AuditAction.TASK_CANCEL,
        task_id=str(task.id),
        tool_id=str(task.tool_id),
        result=AuditResult.SUCCESS,
        project_id=task_project_id(task),
        tool_version_id=task.tool_version_id,
    )


async def _cancel_remote_tool_if_needed(db: AsyncSession | None, *, task: Task) -> None:
    tool_version = task.__dict__.get("tool_version")
    if tool_version is None and db is not None and task.tool_version_id:
        tool_version = await db.get(ToolVersion, task.tool_version_id)
    config = getattr(tool_version, "config", None)
    if not isinstance(config, dict):
        return
    if config.get("type") == "k8s_job":
        external_id = task_external_execution_id(task)
        if not external_id:
            external_id = task_external_execution_id(task)
        if not external_id and db is not None:
            external_id = await task_execution_record_external_id(db, task=task)
        if not external_id:
            return
        from app.execution.runtime import get_execution_service

        await get_execution_service().cancel("k8s_job", external_id)
        return


