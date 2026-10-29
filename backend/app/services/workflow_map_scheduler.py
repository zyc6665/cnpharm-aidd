"""Workflow map node scheduling and reconciliation."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import ValidationException
from app.common.time import utcnow_iso
from app.models.tasks import Task, TaskStatus
from app.models.users import User
from app.models.workflows import WorkflowRun
from app.schemas.tasks import TaskCreate
from app.services.run_preparation import prepare_workflow_node_run
from app.services.workflow_map_items import resolve_map_items
from app.services.workflow_task_lookup import find_existing_workflow_node_task
from app.services.workflow_tool_lookup import load_available_workflow_tool
from app.services.workflow_tool_version import resolve_tool_version


ScheduleTaskFn = Callable[..., Awaitable[Any]]


async def schedule_map_node(
    db: AsyncSession,
    *,
    current_user: User,
    run: WorkflowRun,
    node_id: str,
    node: dict[str, Any],
    node_states: dict[str, Any],
    schedule_task_fn: ScheduleTaskFn,
) -> bool:
    """Create sub-tasks for each map item, respecting max_parallelism."""
    state = dict(node_states.get(node_id) or {})

    over = node.get("over")
    if not over:
        raise ValidationException(f"Map node {node_id} missing 'over' field")

    max_parallelism = int(node.get("max_parallelism", 10))

    sub_tasks: dict[str, dict[str, Any]] = {
        k: dict(v) for k, v in (state.get("sub_tasks") or {}).items()
        if isinstance(v, dict)
    }

    if state.get("map_items") is None:
        items = await resolve_map_items(
            db,
            over=str(over),
            run=run,
            node_states=node_states,
        )
        state["map_items"] = items
        state["map_total"] = len(items)
        state["map_completed"] = sum(
            1 for st in sub_tasks.values()
            if st.get("status") == "success"
        )
        state["map_failed"] = sum(
            1 for st in sub_tasks.values()
            if st.get("status") == "failure"
        )

    items: list[dict[str, Any]] = state["map_items"]

    tool = await load_available_workflow_tool(db, node=node)
    resolved_version_id, _ = resolve_tool_version(state, node, tool)
    base_params = {
        **dict(node.get("params") or {}),
        "workflow_run_id": str(run.id),
        "workflow_node_id": str(node_id),
        "workflow_definition_id": str(run.workflow_definition_id),
        "workflow_node_type": "map",
    }
    prepared = await prepare_workflow_node_run(
        db,
        run=run,
        node_id=node_id,
        node=node,
        node_states=node_states,
        tool=tool,
        current_user=current_user,
        params=base_params,
    )
    if prepared is None:
        return False
    if prepared.binding_decisions:
        state["binding_decisions"] = prepared.binding_decisions
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
    standard_input_uploads = prepared.standard_input_uploads
    prepared_base_params = prepared.params
    state["input_file_ids"] = input_file_ids
    state["input_bindings"] = task_input_bindings

    running_count = sum(
        1 for st in sub_tasks.values()
        if st.get("status") in ("waiting_task", "running")
    )

    scheduled = False
    for i in range(len(items)):
        if running_count >= max_parallelism:
            break

        sub_node_id = f"{node_id}[{i}]"
        existing_sub = sub_tasks.get(sub_node_id, {})

        if existing_sub.get("status") in ("waiting_task", "running", "success", "failure"):
            continue

        node_params = {
            **prepared_base_params,
            "workflow_node_id": str(sub_node_id),
            "workflow_node_type": "map",
            "map_item": items[i],
            "map_index": i,
        }

        existing_task = await find_existing_workflow_node_task(
            db,
            run_id=str(run.id),
            node_id=str(sub_node_id),
        )

        if existing_task:
            sub_tasks[sub_node_id] = {
                "task_id": existing_task.id,
                "status": existing_task.status.lower(),
                "map_index": i,
            }
            running_count += 1
            scheduled = True
            continue

        task = await schedule_task_fn(
            db=db,
            current_user=current_user,
            task_data=TaskCreate(
                name=f"Workflow {run.name} - {sub_node_id}",
                project_id=run.project_id,
                tool_id=tool.id,
                tool_version_id=resolved_version_id,
                params=node_params,
                file_ids=list(input_file_ids),
                input_bindings=task_input_bindings,
                standard_input_uploads=standard_input_uploads,
            ),
        )

        sub_tasks[sub_node_id] = {
            "task_id": task.id,
            "status": "waiting_task",
            "map_index": i,
        }
        running_count += 1
        scheduled = True

    state["sub_tasks"] = sub_tasks

    if state.get("map_completed", 0) + state.get("map_failed", 0) >= len(items):
        state["status"] = "success" if state.get("map_failed", 0) == 0 else "failure"
        state["finished_at"] = utcnow_iso()
    elif scheduled or running_count > 0:
        state["status"] = "waiting_task"
    else:
        state["status"] = state.get("status", "pending")

    node_states[node_id] = state
    return scheduled


async def reconcile_map_sub_tasks(
    db: AsyncSession,
    *,
    node_id: str,
    state: dict[str, Any],
    node_states: dict[str, Any],
    run: WorkflowRun,
) -> bool:
    """Check all map sub-tasks and update the map node state accordingly."""
    sub_tasks: dict[str, dict[str, Any]] = {
        k: dict(v) for k, v in (state.get("sub_tasks") or {}).items()
        if isinstance(v, dict)
    }

    if not sub_tasks:
        return False

    completed = 0
    failed = 0

    for sub_node_id, sub_state in sub_tasks.items():
        if sub_state.get("status") in ("success", "failure"):
            if sub_state.get("status") == "success":
                completed += 1
            else:
                failed += 1
            continue

        task_id = sub_state.get("task_id")
        if not task_id:
            continue

        task_result = await db.execute(
            select(Task)
            .options(selectinload(Task.outputs))
            .where(Task.id == str(task_id))
        )
        task = task_result.scalar_one_or_none()
        if not task:
            sub_state["status"] = "failure"
            sub_state["error_message"] = "Map sub-task not found"
            failed += 1
            continue

        if task.status in {TaskStatus.PENDING.value, TaskStatus.QUEUED.value}:
            # 子任务状态词表只有 pending/running，排队中按 pending 呈现
            sub_state["status"] = "pending"
            continue

        if task.status == TaskStatus.RUNNING.value:
            sub_state["status"] = "running"
            continue

        if task.status in {
            TaskStatus.FAILURE.value,
            TaskStatus.CANCELED.value,
            TaskStatus.TIMEOUT.value,
            # 同 workflow_waiting_task：被拒的 map 子任务等同失败，
            # 否则 map 永远等不到一个不会开始的任务。
            TaskStatus.REJECTED.value,
        }:
            sub_state["status"] = "failure"
            sub_state["error_message"] = task.error_message or "Map sub-task failed"
            failed += 1
        elif task.status == TaskStatus.SUCCESS.value:
            sub_state["status"] = "success"
            completed += 1

        sub_tasks[sub_node_id] = sub_state

    state["sub_tasks"] = sub_tasks
    state["map_completed"] = completed
    state["map_failed"] = failed

    total = state.get("map_total", 0)
    if completed + failed >= total:
        state["status"] = "success" if failed == 0 else "failure"
        if failed > 0:
            state["error_message"] = (
                f"Map node {node_id}: {failed}/{total} sub-tasks failed"
            )
        state["finished_at"] = utcnow_iso()
        node_states[node_id] = state
        return True

    if "status" not in state:
        state["status"] = "waiting_task"
    node_states[node_id] = state
    return False
