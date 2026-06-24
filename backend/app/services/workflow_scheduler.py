"""Workflow node scheduling service."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.time import utcnow, utcnow_iso
from app.common.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.models.files import File as FileModel
from app.models.tasks import Task, TaskInput, TaskStatus
from app.models.tools import Tool, ToolStatus
from app.models.users import User
from app.models.workflows import WorkflowRun
from app.schemas.tasks import TaskCreate
from app.services.semantic_types import normalize_semantic_type
from app.services.workflow_validation import (
    is_tool_node,
    nodes_by_id,
    workflow_dependency_map,
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
            "tool_version_id": (indexed_nodes[current_node_id].get("tool_version") or {}).get("id"),
            "tool_version": indexed_nodes[current_node_id].get("tool_version"),
            "semantic_inputs": dict(indexed_nodes[current_node_id].get("semantic_inputs") or {}),
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
    return all(
        (node_states.get(dependency_id) or {}).get("status") == "success"
        for dependency_id in dependency_tool_node_ids(definition, node_id)
    )


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
    if tool.status != ToolStatus.PUBLISHED.value or tool.is_public is not True:
        raise ValidationException(f"Workflow tool is unavailable: {tool.slug}")
    if not tool.current_version or tool.current_version.is_active is not True:
        raise ValidationException(f"Workflow tool has no active version: {tool.slug}")
    return tool


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
        file_record = await db.get(FileModel, file_id)
        if not file_record:
            raise NotFoundException(f"Workflow input file not found: {semantic_type}")
        if file_id not in seen_file_ids:
            seen_file_ids.add(file_id)
            file_ids.append(file_id)

    return file_ids


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
        "workflow_template_id": str(run.template_id or ""),
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
                TaskStatus.FAILURE.value,
                TaskStatus.CANCELED.value,
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
        if await schedule_workflow_node(
            db,
            current_user=current_user,
            run=run,
            node_id=current_node_id,
            node=indexed_nodes[current_node_id],
            node_states=node_states,
            schedule_task_fn=schedule_task_fn,
        ):
            scheduled_count += 1

    run.node_states = node_states
    if scheduled_count > 0:
        run.status = "waiting_task"
        run.started_at = run.started_at or utcnow()
    elif run.execution_order and all(
        (node_states.get(current_node_id) or {}).get("status") == "success"
        for current_node_id in run.execution_order
    ):
        run.status = "success"
        run.finished_at = utcnow()
    elif run.status == "pending":
        run.status = "pending"

    await db.commit()
    await db.refresh(run)
    return scheduled_count
