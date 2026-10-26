"""Workflow task lookup helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tasks import Task, TaskInput, TaskStatus
from app.models.users import User
from app.models.workflows import WorkflowRun


async def find_existing_workflow_node_task(
    db: AsyncSession,
    *,
    current_user: User,
    run: WorkflowRun,
    node_id: str,
    tool_id: str,
) -> Task | None:
    """Return the latest active task already scheduled for one workflow node."""
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.inputs))
        .join(TaskInput, TaskInput.task_id == Task.id)
        .where(Task.user_id == current_user.id, Task.tool_id == tool_id)
        .order_by(Task.created_at.desc(), Task.id.desc())
        .limit(20)
    )

    for task in result.scalars().all():
        params = task.inputs.params if task.inputs else {}
        if not isinstance(params, dict):
            continue
        if _matches_workflow_node(task, params, run=run, node_id=node_id):
            return task

    return None


def _matches_workflow_node(
    task: Task,
    params: dict,
    *,
    run: WorkflowRun,
    node_id: str,
) -> bool:
    return (
        str(params.get("workflow_run_id") or "") == str(run.id)
        and str(params.get("workflow_node_id") or "") == str(node_id)
        and task.status
        in {
            TaskStatus.PENDING.value,
            TaskStatus.QUEUED.value,
            TaskStatus.RUNNING.value,
            TaskStatus.SUCCESS.value,
        }
    )
