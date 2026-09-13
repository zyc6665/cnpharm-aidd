"""Workflow node scheduling service."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow, utcnow_iso
from app.models.users import User
from app.models.workflows import WorkflowRun
from app.schemas.tasks import TaskCreate
from app.services.workflow_condition_scheduler import schedule_condition_node
from app.services.workflow_dependencies import dependencies_satisfied
from app.services.workflow_loop_scheduler import schedule_loop_node
from app.services.workflow_map_scheduler import schedule_map_node
from app.services.run_preparation import prepare_workflow_node_run
from app.services.workflow_task_lookup import find_existing_workflow_node_task
from app.services.workflow_tool_lookup import load_available_workflow_tool
from app.services.workflow_validation import (
    is_condition_node,
    is_loop_node,
    is_map_node,
    is_tool_node,
    nodes_by_id,
)


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


async def start_ready_workflow_nodes(
    db: AsyncSession,
    *,
    current_user: User,
    run: WorkflowRun,
    schedule_task_fn: ScheduleTaskFn,
) -> int:
    definition = dict(run.definition or {})
    node_states = dict(run.node_states or {})
    indexed_nodes = nodes_by_id(definition)
    scheduled_count = 0

    for current_node_id in run.execution_order or []:
        state = dict(node_states.get(current_node_id) or {})
        if state.get("status") not in {None, "pending", "ready"}:
            continue
        if not dependencies_satisfied(
            definition=definition,
            node_states=node_states,
            node_id=current_node_id,
        ):
            continue

        node = indexed_nodes[current_node_id]
        if is_condition_node(node):
            if await schedule_condition_node(
                run=run,
                node_id=current_node_id,
                node=node,
                node_states=node_states,
            ):
                scheduled_count += 1
        elif is_map_node(node):
            if await schedule_map_node(
                db,
                current_user=current_user,
                run=run,
                node_id=current_node_id,
                node=node,
                node_states=node_states,
                schedule_task_fn=schedule_task_fn,
            ):
                scheduled_count += 1
        elif is_tool_node(node):
            if await schedule_workflow_node(
                db,
                current_user=current_user,
                run=run,
                node_id=current_node_id,
                node=node,
                node_states=node_states,
                schedule_task_fn=schedule_task_fn,
            ):
                scheduled_count += 1
        elif is_loop_node(node):
            if await schedule_loop_node(
                db,
                current_user=current_user,
                run=run,
                node_id=current_node_id,
                node=node,
                node_states=node_states,
                schedule_task_fn=schedule_task_fn,
            ):
                scheduled_count += 1

    run.node_states = node_states
    if scheduled_count > 0:
        run.status = "waiting_task"
        run.started_at = run.started_at or utcnow()
    elif run.execution_order and all(
        (node_states.get(current_node_id) or {}).get("status")
        in {"success", "failure", "skipped"}
        for current_node_id in run.execution_order
    ):
        has_failure = any(
            (node_states.get(current_node_id) or {}).get("status") == "failure"
            for current_node_id in run.execution_order
        )
        run.status = "failure" if has_failure else "success"
        run.finished_at = utcnow()
    elif run.status == "pending":
        run.status = "pending"

    await db.commit()
    await db.refresh(run)
    return scheduled_count
