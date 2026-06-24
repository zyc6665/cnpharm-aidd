"""Workflow service compatibility facade."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import User
from app.models.workflows import WorkflowRun, WorkflowTemplate
from app.schemas.workflows import (
    WorkflowRunCreate,
    WorkflowTemplateCreate,
    WorkflowTemplateDuplicate,
    WorkflowTemplateUpdate,
)
from app.tasks.service import create_and_schedule_tool_task

from app.services.workflow_runs import (
    create_workflow_run as _create_workflow_run,
    get_workflow_run,
    list_workflow_runs,
    load_run_for_user,
    sync_workflow_run as _sync_workflow_run,
)
from app.services.workflow_scheduler import start_ready_workflow_nodes as _start_ready_workflow_nodes
from app.services.workflow_templates import (
    create_workflow_template,
    delete_workflow_template,
    duplicate_workflow_template,
    get_workflow_template,
    list_workflow_templates,
    load_template_for_user,
    update_workflow_template,
)
from app.services.workflow_validation import (
    is_tool_node,
    node_id,
    nodes_by_id,
    required_workflow_inputs,
    validate_workflow_definition,
    workflow_dependency_map,
    workflow_edges,
    workflow_nodes,
)


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
    template_id: str,
    data: WorkflowRunCreate,
) -> WorkflowRun:
    return await _create_workflow_run(
        db,
        current_user=current_user,
        template_id=template_id,
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


__all__ = [
    "create_and_schedule_tool_task",
    "create_workflow_run",
    "create_workflow_template",
    "delete_workflow_template",
    "duplicate_workflow_template",
    "get_workflow_run",
    "get_workflow_template",
    "is_tool_node",
    "list_workflow_runs",
    "list_workflow_templates",
    "load_run_for_user",
    "load_template_for_user",
    "node_id",
    "nodes_by_id",
    "required_workflow_inputs",
    "start_ready_workflow_nodes",
    "sync_workflow_run",
    "update_workflow_template",
    "validate_workflow_definition",
    "workflow_dependency_map",
    "workflow_edges",
    "workflow_nodes",
]
