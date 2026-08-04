"""Workflow node scheduling service."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.time import utcnow, utcnow_iso
from app.common.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.models.files import File as FileModel
from app.models.tasks import Task, TaskInput, TaskStatus
from app.models.tools import Tool, ToolProviderType, ToolStatus
from app.models.users import User
from app.models.workflows import WorkflowRun
from app.schemas.tasks import TaskCreate
from app.services.semantic_types import normalize_semantic_type
from app.services.workflow_artifacts import standard_artifact_file_ids
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


_CONDITION_OPERATORS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: _compare(a, b, lambda x, y: x > y),
    "<": lambda a, b: _compare(a, b, lambda x, y: x < y),
    ">=": lambda a, b: _compare(a, b, lambda x, y: x >= y),
    "<=": lambda a, b: _compare(a, b, lambda x, y: x <= y),
    "in": lambda a, b: a in b if isinstance(b, (list, tuple, str, set, dict)) else False,
    "contains": lambda a, b: b in a if isinstance(a, (list, tuple, str, set, dict)) else False,
}


def _compare(left: Any, right: Any, op: Callable[[Any, Any], bool]) -> bool:
    """带类型安全包装的比较操作。"""
    try:
        return op(left, right)
    except TypeError as exc:
        raise ValidationException(
            f"Cannot compare values of types {type(left).__name__} and {type(right).__name__}"
        ) from exc


def _resolve_value(
    ref: Any,
    *,
    run: WorkflowRun,
    node_states: dict[str, Any],
) -> Any:
    """解析条件表达式中的值引用。"""
    if not isinstance(ref, str):
        return ref

    if ref.startswith("workflow_input:"):
        semantic_key = ref.split(":", 1)[1]
        return (run.input_files or {}).get(semantic_key)

    if ref.startswith("node:"):
        parts = ref.split(":", 2)
        if len(parts) != 3:
            raise ValidationException(f"Invalid node reference: {ref}")
        source_node_id = parts[1]
        source_semantic_type = normalize_semantic_type(parts[2])
        source_state = node_states.get(source_node_id) or {}
        source_output = (source_state.get("semantic_outputs") or {}).get(source_semantic_type)
        if not source_output:
            return None
        # 优先返回 value，否则返回 file_id
        return source_output.get("value", source_output.get("file_id"))

    return ref


def evaluate_condition_expression(
    expression: dict[str, Any],
    *,
    run: WorkflowRun,
    node_states: dict[str, Any],
) -> bool:
    """评估 condition 表达式，返回 True/False。"""
    op = expression.get("op")
    if op not in _CONDITION_OPERATORS:
        raise ValidationException(f"Unsupported condition operator: {op}")

    left_value = _resolve_value(expression.get("left"), run=run, node_states=node_states)
    right_value = _resolve_value(expression.get("right"), run=run, node_states=node_states)

    try:
        return bool(_CONDITION_OPERATORS[op](left_value, right_value))
    except Exception as exc:
        raise ValidationException(
            f"Condition evaluation failed: {op}({left_value!r}, {right_value!r}): {exc}"
        ) from exc


def _mark_node_skipped(
    node_states: dict[str, Any],
    node_id: str,
    reason: str,
) -> None:
    """递归标记节点及其下游为 skipped。"""
    state = dict(node_states.get(node_id) or {})
    if state.get("status") in {"success", "failure", "skipped", "waiting_task"}:
        return
    state.update({
        "status": "skipped",
        "skip_reason": reason,
        "finished_at": utcnow_iso(),
    })
    node_states[node_id] = state


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
            "tool_version_id": (indexed_nodes[current_node_id].get("tool_version") or {}).get("id"),
            "tool_version": indexed_nodes[current_node_id].get("tool_version"),
            "semantic_inputs": dict(indexed_nodes[current_node_id].get("semantic_inputs") or {}),
            "artifact_inputs": dict(indexed_nodes[current_node_id].get("artifact_inputs") or {}),
            "artifact_input_slots": list(indexed_nodes[current_node_id].get("artifact_input_slots") or []),
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


async def resolve_node_input_files(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    node: dict[str, Any],
    node_states: dict[str, Any],
) -> list[str] | None:
    file_ids: list[str] = []
    seen_file_ids: set[str] = set()

    for semantic_type, source in (node.get("semantic_inputs") or {}).items():
        if not isinstance(source, str):
            raise ValidationException(f"Unsupported workflow input source: {source}")

        if source.startswith("workflow_input:"):
            semantic_key = normalize_semantic_type(source.split(":", 1)[1] or str(semantic_type))
            file_id = (run.input_files or {}).get(semantic_key)
            if not file_id:
                raise ValidationException(f"Workflow run is missing required input: {semantic_key}")
        elif source.startswith("node:"):
            parts = source.split(":", 2)
            if len(parts) != 3:
                raise ValidationException(f"Invalid workflow node input source: {source}")
            source_node_id = parts[1]
            source_semantic_type = normalize_semantic_type(parts[2])
            source_state = node_states.get(source_node_id) or {}
            if source_state.get("status") != "success":
                return None
            source_output = (source_state.get("semantic_outputs") or {}).get(source_semantic_type)
            if not source_output:
                return None
            file_id = source_output.get("file_id")
            if not file_id:
                raise ValidationException(
                    "Workflow node output is not file-backed: "
                    f"node={source_node_id}, semantic_type={source_semantic_type}"
                )
        else:
            raise ValidationException(f"Unsupported workflow input source: {source}")

        file_id = str(file_id)
        await _append_existing_file_id(
            db,
            file_ids=file_ids,
            seen_file_ids=seen_file_ids,
            file_id=file_id,
            label=str(semantic_type),
        )

    for slot_name, source in (node.get("artifact_inputs") or {}).items():
        if not isinstance(source, str):
            raise ValidationException(f"Unsupported workflow artifact input source: {source}")

        if source.startswith("workflow_input:"):
            artifact_key = source.split(":", 1)[1] or str(slot_name)
            file_id = (run.input_files or {}).get(artifact_key)
            if not file_id:
                raise ValidationException(f"Workflow run is missing required input: {artifact_key}")
            await _append_existing_file_id(
                db,
                file_ids=file_ids,
                seen_file_ids=seen_file_ids,
                file_id=str(file_id),
                label=str(slot_name),
            )
            continue

        if source.startswith("node:"):
            parts = source.split(":", 2)
            if len(parts) != 3:
                raise ValidationException(f"Invalid workflow artifact input source: {source}")
            source_node_id = parts[1]
            source_output_name = parts[2]
            source_state = node_states.get(source_node_id) or {}
            if source_state.get("status") != "success":
                return None
            artifact_file_ids = standard_artifact_file_ids(
                source_state.get("standard_artifacts") or {},
                source_output_name,
            )
            if not artifact_file_ids:
                return None
            for file_id in artifact_file_ids:
                await _append_existing_file_id(
                    db,
                    file_ids=file_ids,
                    seen_file_ids=seen_file_ids,
                    file_id=file_id,
                    label=str(slot_name),
                )
            continue

        raise ValidationException(f"Unsupported workflow artifact input source: {source}")

    return file_ids


async def _append_existing_file_id(
    db: AsyncSession,
    *,
    file_ids: list[str],
    seen_file_ids: set[str],
    file_id: str,
    label: str,
) -> None:
    file_record = await db.get(FileModel, file_id)
    if not file_record:
        raise NotFoundException(f"Workflow input file not found: {label}")
    if file_id not in seen_file_ids:
        seen_file_ids.add(file_id)
        file_ids.append(file_id)


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

    input_file_ids = await resolve_node_input_files(
        db,
        run=run,
        node=node,
        node_states=node_states,
    )
    if input_file_ids is None:
        return False

    tool = await load_available_workflow_tool(db, node=node)
    node_params = {
        **dict(node.get("params") or {}),
        "workflow_run_id": str(run.id),
        "workflow_node_id": str(node_id),
        "workflow_definition_id": str(run.workflow_definition_id),
        "workflow_node_type": str(node.get("kind") or node.get("type") or "tool"),
    }
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

    # 标记未激活分支的下游节点为 skipped
    for edge in workflow_edges(dict(run.definition or {})):
        if str(edge.get("source") or "") != node_id:
            continue
        branch = edge.get("branch")
        if not branch:
            continue
        target = str(edge.get("target") or "")
        if branch != active_branch:
            _mark_node_skipped(node_states, target, f"Branch '{branch}' not active")

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


async def _resolve_map_items(
    db: AsyncSession,
    *,
    over: str,
    run: WorkflowRun,
    node_states: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve the map node *over* reference to a list of items."""
    if over.startswith("workflow_input:"):
        key = over.split(":", 1)[1]
        raw = (run.input_files or {}).get(key)
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return list(raw.values())
        return [raw] if raw is not None else []

    if over.startswith("node:"):
        parts = over.split(":", 2)
        if len(parts) != 3:
            raise ValidationException(f"Invalid map over reference: {over}")
        source_node_id = parts[1]
        source_semantic_type = normalize_semantic_type(parts[2])
        source_state = node_states.get(source_node_id) or {}
        source_output = (source_state.get("semantic_outputs") or {}).get(source_semantic_type)
        if not source_output:
            return []

        value = source_output.get("value")
        if isinstance(value, list):
            return value

        file_id = source_output.get("file_id")
        if file_id:
            file_record = await db.get(FileModel, str(file_id))
            if file_record and file_record.storage_path:
                path = Path(file_record.storage_path)
                try:
                    if path.suffix == ".csv":
                        text = path.read_text(encoding="utf-8")
                        reader = csv.DictReader(io.StringIO(text))
                        return list(reader)
                    if path.suffix == ".json":
                        data = json.loads(path.read_text(encoding="utf-8"))
                        return data if isinstance(data, list) else [data]
                except (OSError, json.JSONDecodeError, csv.Error):
                    return [source_output]
        return [source_output]

    raise ValidationException(f"Unsupported map over reference: {over}")


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
        items = await _resolve_map_items(
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
    input_file_ids = await resolve_node_input_files(
        db,
        run=run,
        node=node,
        node_states=node_states,
    )
    if input_file_ids is None:
        return False

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
            **dict(node.get("params") or {}),
            "workflow_run_id": str(run.id),
            "workflow_node_id": str(sub_node_id),
            "workflow_definition_id": str(run.workflow_definition_id),
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

    # 为当前迭代创建 body 节点任务
    input_file_ids = await resolve_node_input_files(
        db,
        run=run,
        node=node,
        node_states=node_states,
    )
    if input_file_ids is None:
        return False

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
                file_ids=list(input_file_ids),
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


def _evaluate_convergence(
    condition: dict[str, Any] | None,
    *,
    body_states: dict[str, Any],
    previous_iteration_outputs: dict[str, Any] | None = None,
) -> bool:
    """评估循环收敛条件。

    支持从 body 节点输出中读取值（使用 ``node:<body_node_id>:<field>`` 语法）。
    未提供 convergence_condition 时使用 previous_iteration_outputs 判断迭代间变化。
    """
    if not condition:
        if previous_iteration_outputs and body_states:
            return body_states == previous_iteration_outputs
        return False

    op = condition.get("op")
    left_raw = condition.get("left")
    right_raw = condition.get("right")

    left = _resolve_loop_value(left_raw, body_states)
    right = _resolve_loop_value(right_raw, body_states)

    # loop 收敛评估使用直接比较（不通过 _CONDITION_OPERATORS 的 _compare 封装，
    # 因为 _compare 在类型不匹配时抛 ValidationException 而非返回 False）
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "<":
        try:
            return left < right
        except TypeError:
            return False
    if op == ">":
        try:
            return left > right
        except TypeError:
            return False
    if op == "<=":
        try:
            return left <= right
        except TypeError:
            return False
    if op == ">=":
        try:
            return left >= right
        except TypeError:
            return False
    if op == "in":
        try:
            return left in right
        except TypeError:
            return False
    if op == "contains":
        try:
            return right in left
        except TypeError:
            return False
    return False


def _resolve_loop_value(raw: Any, body_states: dict[str, Any]) -> Any:
    """解析收敛条件中的值引用。

    支持 ``node:<body_node_id>:<output_key>`` 格式从 body 节点输出中读取。
    """
    if isinstance(raw, str) and raw.startswith("node:"):
        parts = raw.split(":", 2)
        if len(parts) == 3:
            node_ref = parts[1]
            output_key = parts[2]
            node_state = body_states.get(node_ref, {})
            outputs = node_state.get("outputs") or node_state.get("result") or {}
            if isinstance(outputs, dict):
                return outputs.get(output_key)
            return None
    return raw


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
    converged = _evaluate_convergence(
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


async def find_existing_workflow_node_task(
    db: AsyncSession,
    *,
    current_user: User,
    run: WorkflowRun,
    node_id: str,
    tool_id: str,
) -> Task | None:
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.inputs))
        .join(TaskInput, TaskInput.task_id == Task.id)
        .where(Task.user_id == current_user.id, Task.tool_id == tool_id)
        .order_by(Task.created_at.desc(), Task.id.desc())
        .limit(20)
    )
    tasks = list(result.scalars().all())

    for task in tasks:
        params = task.inputs.params if task.inputs else {}
        if not isinstance(params, dict):
            continue
        if (
            str(params.get("workflow_run_id") or "") == str(run.id)
            and str(params.get("workflow_node_id") or "") == str(node_id)
            and task.status in {
                TaskStatus.PENDING.value,
                TaskStatus.RUNNING.value,
                TaskStatus.SUCCESS.value,
            }
        ):
            return task

    return None


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
