"""Workflow tool node scheduling."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow_iso
from app.models.users import User
from app.models.workflows import WorkflowRun
from app.schemas.tasks import TaskCreate
from app.services.run_preparation import prepare_workflow_node_run
from app.services.workflow_task_lookup import find_existing_workflow_node_task
from app.services.workflow_tool_lookup import load_available_workflow_tool


ScheduleTaskFn = Callable[..., Awaitable[Any]]


async def schedule_workflow_node(
    db: AsyncSession,
    *,
    current_user: User,
    run: WorkflowRun,
    node_id: str,
    node: dict[str, Any],
    node_states: dict[str, Any],
    schedule_task_fn: ScheduleTaskFn,
) -> bool:
    """Prepare inputs and schedule one plain tool node."""
    state = dict(node_states.get(node_id) or {})
    if state.get("task_id"):
        state["status"] = "waiting_task"
        node_states[node_id] = state
        return False

    tool = await load_available_workflow_tool(db, node=node)
    node_params = {
        **dict(node.get("params") or {}),
        "workflow_run_id": str(run.id),
        "workflow_node_id": str(node_id),
        "workflow_definition_id": str(run.workflow_definition_id),
        "workflow_node_type": str(node.get("kind") or node.get("type") or "tool"),
    }
    prepared = await prepare_workflow_node_run(
        db,
        run=run,
        node_id=node_id,
        node=node,
        node_states=node_states,
        tool=tool,
        current_user=current_user,
        params=node_params,
    )
    if prepared is None:
        return False
    if prepared.binding_decisions:
        state["binding_decisions"] = prepared.binding_decisions
        node_states[node_id] = state
    if not prepared.ready:
        state.update(
            {
                "status": "blocked",
                "blocked_reason": prepared.blocked_reason,
                "finished_at": utcnow_iso(),
            }
        )
        node_states[node_id] = state
        return False

    input_file_ids = prepared.file_ids
    task_input_bindings = prepared.input_bindings
    node_params = prepared.params
    existing_task = await find_existing_workflow_node_task(
        db,
        current_user=current_user,
        run=run,
        node_id=node_id,
        tool_id=str(tool.id),
    )
    if existing_task:
        state.update(
            {
                "status": "waiting_task",
                "tool_id": tool.id,
                "tool_slug": tool.slug,
                "tool_version_id": tool.current_version_id,
                "tool_version": {
                    "id": tool.current_version_id,
                    "version": tool.current_version.version if tool.current_version else None,
                },
                "task_id": existing_task.id,
                "input_file_ids": input_file_ids,
                "input_bindings": task_input_bindings,
                "params": node_params,
                "started_at": state.get("started_at") or utcnow_iso(),
            }
        )
        node_states[node_id] = state
        return False

    task = await schedule_task_fn(
        db=db,
        current_user=current_user,
        task_data=TaskCreate(
            name=f"Workflow {run.name} - {node_id}",
            project_id=run.project_id,
            tool_id=tool.id,
            tool_version_id=tool.current_version_id,
            params=node_params,
            file_ids=input_file_ids,
            input_bindings=task_input_bindings,
            standard_input_uploads=prepared.standard_input_uploads,
        ),
    )

    state = dict(node_states.get(node_id) or {})
    state.update(
        {
            "status": "waiting_task",
            "tool_id": tool.id,
            "tool_slug": tool.slug,
            "tool_version_id": tool.current_version_id,
            "tool_version": {
                "id": tool.current_version_id,
                "version": tool.current_version.version if tool.current_version else None,
            },
            "task_id": task.id,
            "input_file_ids": input_file_ids,
            "input_bindings": task_input_bindings,
            "params": node_params,
            "started_at": utcnow_iso(),
        }
    )
    node_states[node_id] = state
    return True
