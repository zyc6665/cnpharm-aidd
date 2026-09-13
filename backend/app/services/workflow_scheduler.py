"""Workflow node scheduling service."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.time import utcnow, utcnow_iso
from app.common.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.models.files import File as FileModel
from app.models.tasks import Task, TaskStatus
from app.models.tools import Tool, ToolProviderType, ToolStatus
from app.models.users import User
from app.models.workflows import WorkflowRun
from app.schemas.tasks import TaskCreate
from app.services.workflow_conditions import evaluate_condition_expression
from app.services.workflow_loop_convergence import evaluate_loop_convergence
from app.services.workflow_map_items import resolve_map_items
from app.services.run_preparation import prepare_workflow_node_run
from app.services.semantic_types import normalize_semantic_type
from app.services.workflow_skip import mark_unreachable_nodes_skipped
from app.services.workflow_task_lookup import find_existing_workflow_node_task
from app.services.workflow_validation import (
    is_condition_node,
    is_loop_node,
    is_map_node,
    is_tool_node,
    nodes_by_id,
    workflow_dependency_map,
    workflow_edges,
)


ScheduleTaskFn = Callable[..., Awaitable[Any]]


async def validate_input_files(
    db: AsyncSession,
    *,
    current_user: User,
    input_files: dict[str, str],
) -> dict[str, str]:
    normalized = {
        normalize_semantic_type(str(semantic_type)): str(file_id)
        for semantic_type, file_id in input_files.items()
        if file_id
    }
    for semantic_type, file_id in normalized.items():
        file_record = await db.get(FileModel, file_id)
        if not file_record:
            raise NotFoundException(f"Workflow input file not found: {semantic_type}")
        if file_record.owner_id != current_user.id and current_user.role != "admin":
            raise ForbiddenException(f"No permission to use workflow input file: {semantic_type}")
    return normalized


def initial_node_states(definition: dict[str, Any], execution_order: list[str]) -> dict[str, Any]:
    indexed_nodes = nodes_by_id(definition)
    return {
        current_node_id: {
            "status": "pending",
            "tool_slug": indexed_nodes[current_node_id].get("tool_slug"),
            "tool_id": indexed_nodes[current_node_id].get("tool_id"),
            "tool_version_id": (
                indexed_nodes[current_node_id].get("tool_version") or {}
            ).get("id"),
            "tool_version": indexed_nodes[current_node_id].get("tool_version"),
            "semantic_inputs": dict(indexed_nodes[current_node_id].get("semantic_inputs") or {}),
            "artifact_inputs": dict(indexed_nodes[current_node_id].get("artifact_inputs") or {}),
            "artifact_input_slots": list(
                indexed_nodes[current_node_id].get("artifact_input_slots") or []
            ),
            "artifact_outputs": list(indexed_nodes[current_node_id].get("artifact_outputs") or []),
            "params": dict(indexed_nodes[current_node_id].get("params") or {}),
        }
        for current_node_id in execution_order
    }


def dependency_tool_node_ids(definition: dict[str, Any], node_id: str) -> set[str]:
    indexed_nodes = nodes_by_id(definition)
    dependencies = workflow_dependency_map(definition)
    return {
        source
        for source in dependencies.get(node_id, set())
        if is_tool_node(indexed_nodes.get(source))
    }


def dependencies_satisfied(
    *,
    definition: dict[str, Any],
    node_states: dict[str, Any],
    node_id: str,
) -> bool:
    indexed_nodes = nodes_by_id(definition)

    # 检查默认依赖是否 success
    for dependency_id in dependency_tool_node_ids(definition, node_id):
        if (node_states.get(dependency_id) or {}).get("status") != "success":
            return False

    # 对 condition 分支的下游节点，检查分支是否激活
    for edge in workflow_edges(definition):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if target != node_id:
            continue
        branch = edge.get("branch")
        if not branch or not is_condition_node(indexed_nodes.get(source)):
            continue
        source_state = node_states.get(source) or {}
        if source_state.get("status") != "success":
            return False
        active_branch = source_state.get("active_branch")
        if active_branch and branch != active_branch:
            return False

    return True


async def load_available_workflow_tool(
    db: AsyncSession,
    *,
    node: dict[str, Any],
) -> Tool:
    tool_id = node.get("tool_id")
    tool_slug = node.get("tool_slug")
    query = select(Tool).options(selectinload(Tool.current_version))
    if tool_id:
        query = query.where(Tool.id == str(tool_id))
    elif tool_slug:
        query = query.where(Tool.slug == str(tool_slug))
    else:
        raise ValidationException("Workflow tool node is missing tool_id or tool_slug")

    result = await db.execute(query)
    tool = result.scalar_one_or_none()
    if not tool:
        raise ValidationException(f"Workflow tool is not configured: {tool_slug or tool_id}")
    if tool.status != ToolStatus.PUBLISHED.value or (
        tool.is_public is not True and not _is_private_platform_builtin(tool)
    ):
        raise ValidationException(f"Workflow tool is unavailable: {tool.slug}")
    if (
        not tool.current_version
        or tool.current_version.is_active is not True
        or tool.current_version.deprecated is True
    ):
        raise ValidationException(f"Workflow tool has no active version: {tool.slug}")
    return tool


def _is_private_platform_builtin(tool: Tool) -> bool:
    current_version = tool.current_version
    config = current_version.config if current_version and current_version.config else {}
    return (
        tool.provider_type == ToolProviderType.PLATFORM.value
        and isinstance(config, dict)
        and config.get("type") == "builtin"
    )


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


async def schedule_condition_node(
    *,
    run: WorkflowRun,
    node_id: str,
    node: dict[str, Any],
    node_states: dict[str, Any],
) -> bool:
    """评估 condition 节点，设置 active_branch，并跳过未激活分支。"""
    expression = node.get("expression")
    if not expression:
        raise ValidationException(f"Condition node {node_id} missing expression")

    try:
        result = evaluate_condition_expression(
            expression,
            run=run,
            node_states=node_states,
        )
    except ValidationException:
        raise
    except Exception as exc:
        state = dict(node_states.get(node_id) or {})
        state.update({
            "status": "failure",
            "error_message": f"Condition evaluation error: {exc}",
            "finished_at": utcnow_iso(),
        })
        node_states[node_id] = state
        return False

    active_branch = "true" if result else "false"
    definition = dict(run.definition or {})

    # 标记未激活分支的下游节点为 skipped
    for edge in workflow_edges(definition):
        if str(edge.get("source") or "") != node_id:
            continue
        branch = edge.get("branch")
        if not branch:
            continue
        target = str(edge.get("target") or "")
        if branch != active_branch:
            mark_unreachable_nodes_skipped(
                node_states,
                target,
                f"Branch '{branch}' not active",
                definition=definition,
            )

    state = dict(node_states.get(node_id) or {})
    state.update({
        "status": "success",
        "active_branch": active_branch,
        "result": result,
        "finished_at": utcnow_iso(),
    })
    node_states[node_id] = state
    return True


# ---------------------------------------------------------------------------
# Map node scheduling
# ---------------------------------------------------------------------------


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

    # First invocation: resolve items
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

    # Count currently running / waiting sub-tasks
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
            current_user=current_user,
            run=run,
            node_id=sub_node_id,
            tool_id=str(tool.id),
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
                tool_version_id=tool.current_version_id,
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

        if task.status in {TaskStatus.PENDING.value, TaskStatus.RUNNING.value}:
            sub_state["status"] = task.status.lower()
            continue

        if task.status in {TaskStatus.FAILURE.value, TaskStatus.CANCELED.value}:
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

    # Preserve existing status if not all done
    if "status" not in state:
        state["status"] = "waiting_task"
    node_states[node_id] = state
    return False


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
    """调度 loop 节点的首次迭代。

    初始化 loop state，为 body 中所有工具节点创建任务。
    """
    body: list[dict[str, Any]] = [dict(bn) for bn in node.get("body") or []]
    if not body:
        state = node_states.get(node_id) or {}
        state["status"] = "failure"
        state["error_message"] = "Loop node has no body nodes"
        node_states[node_id] = state
        return False

    max_iterations = int(node.get("max_iterations") or 10)
    state = dict(node_states.get(node_id) or {})

    # 首次迭代：初始化 loop state
    if "loop_iteration" not in state:
        state["loop_iteration"] = 1
        state["loop_max_iterations"] = max_iterations
        state["loop_body_states"] = {}
        state["loop_history"] = []

    iteration = state["loop_iteration"]

    scheduled = False
    for i, body_node in enumerate(body):
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
    """检查 loop body 中各节点任务状态，决定继续迭代或结束。

    Returns:
        True 如果 loop 已完成（成功或失败），False 如果仍在等待。
    """
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

        if task.status in {TaskStatus.PENDING.value, TaskStatus.RUNNING.value}:
            sub_state["status"] = task.status.lower()
            all_done = False
            body_states[body_node_id] = sub_state
            continue

        if task.status in {TaskStatus.FAILURE.value, TaskStatus.CANCELED.value}:
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

    # 当前迭代所有 body 节点完成
    iteration = state.get("loop_iteration", 1)
    max_iterations = state.get("loop_max_iterations", 10)

    # 保存历史输出（用于收敛判断）
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

    # 检查收敛条件
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
        # 将最后一轮输出合并为 loop 的输出
        merged_outputs: dict[str, Any] = {}
        for bn_id, result in current_outputs.items():
            if isinstance(result, dict):
                merged_outputs.update(result)
        state["semantic_outputs"] = merged_outputs
        node_states[node_id] = state
        return True

    # 下一轮迭代
    state["loop_iteration"] = iteration + 1
    # 重置 body 状态
    state["loop_body_states"] = {}
    state["status"] = "pending"  # 需要重新调度
    node_states[node_id] = state
    return False


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
