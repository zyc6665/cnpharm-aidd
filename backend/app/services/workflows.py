"""Workflow orchestration facade.

This module only contains cross-cutting orchestration functions that need to
wire together multiple workflow sub-services. Concrete CRUD and validation
helpers live in:

- app.services.workflow_runs
- app.services.workflow_validation
- app.services.workflow_scheduler
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import User
from app.models.workflows import WorkflowRun
from app.schemas.workflows import WorkflowRunCreate
from app.tasks.service import create_and_schedule_tool_task

from app.services.workflow_runs import (
    cancel_workflow_run as _cancel_workflow_run,
    create_workflow_run as _create_workflow_run,
    retry_workflow_run_node as _retry_workflow_run_node,
    sync_workflow_run as _sync_workflow_run,
)
from app.services.workflow_scheduler import start_ready_workflow_nodes as _start_ready_workflow_nodes


async def start_ready_workflow_nodes(
    db: AsyncSession,
    *,
    current_user: User,
    run: WorkflowRun,
) -> int:
    return await _start_ready_workflow_nodes(
        db,
        current_user=current_user,
        run=run,
        schedule_task_fn=create_and_schedule_tool_task,
    )


async def create_workflow_run(
    db: AsyncSession,
    *,
    current_user: User,
    workflow_definition_id: str,
    data: WorkflowRunCreate,
) -> WorkflowRun:
    return await _create_workflow_run(
        db,
        current_user=current_user,
        workflow_definition_id=workflow_definition_id,
        data=data,
        schedule_task_fn=create_and_schedule_tool_task,
    )


async def sync_workflow_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
) -> WorkflowRun:
    return await _sync_workflow_run(
        db,
        current_user=current_user,
        run_id=run_id,
        schedule_task_fn=create_and_schedule_tool_task,
    )


async def cancel_workflow_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
) -> WorkflowRun:
    return await _cancel_workflow_run(
        db,
        current_user=current_user,
        run_id=run_id,
    )


async def retry_workflow_run_node(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
    node_id: str,
) -> WorkflowRun:
    return await _retry_workflow_run_node(
        db,
        current_user=current_user,
        run_id=run_id,
        node_id=node_id,
        schedule_task_fn=create_and_schedule_tool_task,
    )


__all__ = [
    "cancel_workflow_run",
    "create_workflow_run",
    "retry_workflow_run_node",
    "start_ready_workflow_nodes",
    "sync_workflow_run",
]
