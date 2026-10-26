"""Workflow loop node scheduling and reconciliation."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.time import utcnow_iso
from app.models.tasks import Task, TaskStatus
from app.models.users import User
from app.models.workflows import WorkflowRun
from app.schemas.tasks import TaskCreate
from app.services.run_preparation import prepare_workflow_node_run
from app.services.workflow_loop_convergence import evaluate_loop_convergence
from app.services.workflow_task_lookup import find_existing_workflow_node_task
from app.services.workflow_tool_lookup import load_available_workflow_tool


ScheduleTaskFn = Callable[..., Awaitable[Any]]


async def schedule_loop_node(
    db: AsyncSession,
    *,
    current_user: User,
    run: WorkflowRun,
    node_id: str,
    node: dict[str, Any],
    node_states: dict[str, Any],
    schedule_task_fn: ScheduleTaskFn,
) -> bool:
    """调度 loop 节点的首次迭代。"""
    body: list[dict[str, Any]] = [dict(bn) for bn in node.get("body") or []]
    if not body:
        state = node_states.get(node_id) or {}
        state["status"] = "failure"
        state["error_message"] = "Loop node has no body nodes"
        node_states[node_id] = state
        return False

    max_iterations = int(node.get("max_iterations") or 10)
    state = dict(node_states.get(node_id) or {})

    if "loop_iteration" not in state:
        state["loop_iteration"] = 1
        state["loop_max_iterations"] = max_iterations
        state["loop_body_states"] = {}
        state["loop_history"] = []

    iteration = state["loop_iteration"]

    scheduled = False
    for body_node in body:
        body_node_id = body_node.get("id")
        sub_node_id = f"{node_id}/{body_node_id}[{iteration}]"
        body_states: dict[str, Any] = state.setdefault("loop_body_states", {})
        existing = body_states.get(body_node_id, {})

        if existing.get("status") in ("waiting_task", "running", "success", "failure"):
            continue

        tool = await load_available_workflow_tool(db, node=body_node)
        node_params = {
            **dict(body_node.get("params") or {}),
            "workflow_run_id": str(run.id),
            "workflow_node_id": str(sub_node_id),
            "workflow_definition_id": str(run.workflow_definition_id),
            "workflow_node_type": "loop_body",
            "loop_iteration": iteration,
        }

        preparation_node = {
            **body_node,
            "semantic_inputs": dict(node.get("semantic_inputs") or {}),
            "artifact_inputs": dict(node.get("artifact_inputs") or {}),
            "artifact_input_slots": list(node.get("artifact_input_slots") or []),
        }
        prepared = await prepare_workflow_node_run(
            db,
            run=run,
            node_id=sub_node_id,
            node=preparation_node,
            node_states=node_states,
            tool=tool,
            current_user=current_user,
            params=node_params,
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
        state["input_file_ids"] = prepared.file_ids
        state["input_bindings"] = prepared.input_bindings
        node_params = prepared.params

        existing_task = await find_existing_workflow_node_task(
            db,
            current_user=current_user,
            run=run,
            node_id=sub_node_id,
            tool_id=str(tool.id),
        )

        if existing_task:
            body_states[body_node_id] = {
                "task_id": existing_task.id,
                "status": existing_task.status,
            }
            scheduled = True
            continue

        task = await schedule_task_fn(
            db=db,
            current_user=current_user,
            task_data=TaskCreate(
                name=f"Workflow {run.name} - {sub_node_id}",
                project_id=run.project_id,
                tool_id=tool.id,
                tool_version_id=tool.current_version_id,
                params=node_params,
                file_ids=list(prepared.file_ids),
                input_bindings=prepared.input_bindings,
                standard_input_uploads=prepared.standard_input_uploads,
            ),
        )

        body_states[body_node_id] = {
            "task_id": task.id,
            "status": "waiting_task",
        }
        scheduled = True

    state["loop_body_states"] = body_states

    if scheduled:
        state["status"] = "waiting_task"
    elif state.get("status") != "waiting_task":
        state["status"] = state.get("status", "pending")

    node_states[node_id] = state
    return scheduled


async def reconcile_loop_body(
    db: AsyncSession,
    *,
    node_id: str,
    node: dict[str, Any],
    state: dict[str, Any],
    node_states: dict[str, Any],
    run: WorkflowRun,
) -> bool:
    """检查 loop body 任务状态，决定继续迭代或结束。"""
    body: list[dict[str, Any]] = [dict(bn) for bn in node.get("body") or []]
    body_states: dict[str, Any] = dict(state.get("loop_body_states") or {})

    if not body or not body_states:
        return False

    all_done = True
    any_failed = False

    for body_node in body:
        body_node_id = body_node.get("id")
        sub_state = dict(body_states.get(body_node_id) or {})

        if sub_state.get("status") in ("success", "failure"):
            if sub_state.get("status") == "failure":
                any_failed = True
            continue

        task_id = sub_state.get("task_id")
        if not task_id:
            all_done = False
            continue

        task_result = await db.execute(
            select(Task)
            .options(selectinload(Task.outputs))
            .where(Task.id == str(task_id))
        )
        task = task_result.scalar_one_or_none()
        if not task:
            sub_state["status"] = "failure"
            sub_state["error_message"] = "Loop body task not found"
            any_failed = True
            body_states[body_node_id] = sub_state
            continue

        if task.status in {TaskStatus.PENDING.value, TaskStatus.QUEUED.value}:
            # 节点状态词表只有 pending/running，排队中按 pending 呈现
            sub_state["status"] = "pending"
            all_done = False
            body_states[body_node_id] = sub_state
            continue

        if task.status == TaskStatus.RUNNING.value:
            sub_state["status"] = "running"
            all_done = False
            body_states[body_node_id] = sub_state
            continue

        if task.status in {
            TaskStatus.FAILURE.value,
            TaskStatus.CANCELED.value,
            TaskStatus.TIMEOUT.value,
        }:
            sub_state["status"] = "failure"
            sub_state["error_message"] = task.error_message or "Loop body task failed"
            any_failed = True
        elif task.status == TaskStatus.SUCCESS.value:
            sub_state["status"] = "success"
            if task.outputs and task.outputs.result:
                sub_state["result"] = task.outputs.result

        body_states[body_node_id] = sub_state

    state["loop_body_states"] = body_states

    if any_failed:
        state["status"] = "failure"
        state["error_message"] = (
            f"Loop node {node_id} iteration {state.get('loop_iteration')} failed"
        )
        state["finished_at"] = utcnow_iso()
        node_states[node_id] = state
        return True

    if not all_done:
        state["status"] = "waiting_task"
        node_states[node_id] = state
        return False

    iteration = state.get("loop_iteration", 1)
    max_iterations = state.get("loop_max_iterations", 10)

    history: list[dict[str, Any]] = state.get("loop_history") or []
    current_outputs = {
        bn_id: bs.get("result")
        for bn_id, bs in body_states.items()
    }
    history.append({
        "iteration": iteration,
        "outputs": current_outputs,
    })
    state["loop_history"] = history

    previous_outputs = history[-2].get("outputs") if len(history) >= 2 else None

    converged = evaluate_loop_convergence(
        node.get("convergence_condition"),
        body_states=body_states,
        previous_iteration_outputs=previous_outputs,
    )

    if converged or iteration >= max_iterations:
        state["status"] = "success"
        state["loop_converged"] = converged
        state["loop_total_iterations"] = iteration
        state["finished_at"] = utcnow_iso()
        merged_outputs: dict[str, Any] = {}
        for result in current_outputs.values():
            if isinstance(result, dict):
                merged_outputs.update(result)
        state["semantic_outputs"] = merged_outputs
        node_states[node_id] = state
        return True

    state["loop_iteration"] = iteration + 1
    state["loop_body_states"] = {}
    state["status"] = "pending"
    node_states[node_id] = state
    return False
