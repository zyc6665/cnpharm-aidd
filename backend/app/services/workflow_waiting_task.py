"""Workflow waiting task resolution."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tasks import Task, TaskStatus
from app.models.workflows import WorkflowRun
from app.services.workflow_run_failures import mark_workflow_node_failed


async def load_finished_workflow_node_task(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    node_states: dict[str, Any],
    node_id: str,
    state: dict[str, Any],
) -> Task | None:
    task_id = state.get("task_id")
    if not task_id:
        mark_workflow_node_failed(
            run,
            node_states=node_states,
            node_id=node_id,
            state=state,
            error_message="Workflow node is waiting without a task id",
        )
        return None

    task_result = await db.execute(
        select(Task)
        .options(selectinload(Task.outputs))
        .where(Task.id == str(task_id))
    )
    task = task_result.scalar_one_or_none()
    if not task:
        mark_workflow_node_failed(
            run,
            node_states=node_states,
            node_id=node_id,
            state=state,
            error_message="Workflow node task not found",
        )
        return None

    if task.status in {
        TaskStatus.PENDING.value,
        TaskStatus.QUEUED.value,
        TaskStatus.RUNNING.value,
    }:
        return None

    if task.status in {
        TaskStatus.FAILURE.value,
        TaskStatus.CANCELED.value,
        TaskStatus.TIMEOUT.value,
    }:
        mark_workflow_node_failed(
            run,
            node_states=node_states,
            node_id=node_id,
            state=state,
            error_message=task.error_message or "Workflow node task failed",
        )
        return None

    return task
