"""Reusable platform task cancellation."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import use_direct_task_execution
from app.execution.records import finish_task_execution_record
from app.logging.audit import AuditAction, AuditResult, get_audit_logger
from app.models.tasks import Task, TaskStatus
from app.models.tools import ToolVersion
from app.models.users import User
from app.remote_tools.invocation import recorded_remote_run_id
from app.tasks.executors.remote_api import RemoteAPIExecutor
from app.tasks.direct_runner import direct_task_runner as default_direct_task_runner
from app.common.task_context import task_project_id
from app.tasks.state_machine import TaskStateMachine


logger = logging.getLogger(__name__)


async def cancel_platform_task(
    db: AsyncSession,
    *,
    task: Task,
    current_user: User,
    direct_runner=default_direct_task_runner,
) -> bool:
    """Cancel a pending or running task through its configured execution backend."""
    if task.status not in {TaskStatus.PENDING.value, TaskStatus.RUNNING.value}:
        return False

    await _cancel_remote_tool_if_needed(db, task=task)

    if use_direct_task_execution():
        direct_runner.cancel_task(str(task.id))
    elif task.celery_task_id:
        from app.tasks.queue_manager import TaskQueueManager

        TaskQueueManager.revoke_task(task.celery_task_id)

    TaskStateMachine.cancel(task)
    try:
        await finish_task_execution_record(
            db,
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
    if config.get("type") != "remote_api" or config.get("mode") != "remote_tool_v1":
        return
    if not recorded_remote_run_id(task.extra_data):
        return
    await RemoteAPIExecutor(task, tool_version, config=config).cancel_remote_run()
