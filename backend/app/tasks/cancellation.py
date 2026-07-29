"""Reusable platform task cancellation."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import use_direct_task_execution
from app.models.tasks import Task, TaskStatus
from app.models.users import User
from app.tasks.direct_runner import direct_task_runner as default_direct_task_runner
from app.tasks.state_machine import TaskStateMachine


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

    if use_direct_task_execution():
        direct_runner.cancel_task(str(task.id))
    elif task.celery_task_id:
        from app.tasks.queue_manager import TaskQueueManager

        TaskQueueManager.revoke_task(task.celery_task_id)

    TaskStateMachine.cancel(task)
    return True
