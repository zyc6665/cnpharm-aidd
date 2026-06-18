"""Workflow persistence and preflight service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.aidd.outputs import extract_semantic_outputs
from app.agents.aidd.registry import load_tool_capability
from app.common.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.models.files import File as FileModel
from app.models.tasks import Task, TaskStatus
from app.models.tools import Tool, ToolStatus
from app.models.users import User
from app.models.workflows import WorkflowRun, WorkflowTemplate
from app.schemas.tasks import TaskCreate
from app.schemas.workflows import (
    WorkflowRunCreate,
    WorkflowTemplateCreate,
    WorkflowTemplateDuplicate,
    WorkflowTemplateUpdate,
)
from app.services.semantic_types import normalize_semantic_type
from app.tasks.service import create_and_schedule_tool_task


def _workflow_nodes(definition: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = definition.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValidationException("Workflow definition must include nodes")
    return [node for node in nodes if isinstance(node, dict)]


def _workflow_edges(definition: dict[str, Any]) -> list[dict[str, Any]]:
    edges = definition.get("edges", [])
    if not isinstance(edges, list):
        raise ValidationException("Workflow definition edges must be a list")
    return [edge for edge in edges if isinstance(edge, dict)]


def _node_id(node: dict[str, Any]) -> str:
    return str(node.get("id") or "")


def _nodes_by_id(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {_node_id(node): node for node in _workflow_nodes(definition)}


def _is_tool_node(node: dict[str, Any] | None) -> bool:
    if not node:
        return False
    node_kind = str(node.get("kind") or node.get("type") or "")
    return node_kind == "tool" or bool(node.get("tool_slug") or node.get("tool_id"))


def _semantic_node_dependency_ids(
    node: dict[str, Any],
    *,
    node_id_set: set[str],
) -> set[str]:
    dependencies: set[str] = set()
    for source in (node.get("semantic_inputs") or {}).values():
        if not isinstance(source, str) or not source.startswith("node:"):
            continue
        parts = source.split(":", 2)
        if len(parts) != 3 or parts[1] not in node_id_set:
            raise ValidationException(f"Workflow semantic input references unknown node: {source}")
        dependencies.add(parts[1])
    return dependencies


def _workflow_dependency_map(definition: dict[str, Any]) -> dict[str, set[str]]:
    nodes = _workflow_nodes(definition)
    node_ids = [_node_id(node) for node in nodes]
    node_id_set = set(node_ids)
    if any(not node_id for node_id in node_ids):
        raise ValidationException("Workflow node id is required")
    if len(node_ids) != len(set(node_ids)):
        raise ValidationException("Workflow node ids must be unique")

    dependencies = {node_id: set() for node_id in node_ids}

    for edge in _workflow_edges(definition):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in node_id_set or target not in node_id_set:
            raise ValidationException("Workflow edge references unknown node")
        dependencies[target].add(source)

    for node in nodes:
        target = _node_id(node)
        dependencies[target].update(
            _semantic_node_dependency_ids(node, node_id_set=node_id_set)
        )

    return dependencies


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


def _file_download_url(file_id: str) -> str:
    return f"/api/v1/files/{file_id}/download"


def _validate_workflow_definition(definition: dict[str, Any]) -> list[str]:
    nodes = _workflow_nodes(definition)
    node_ids = [_node_id(node) for node in nodes]
    dependencies = _workflow_dependency_map(definition)
    adjacency = {node_id: [] for node_id in node_ids}
    indegree = {node_id: 0 for node_id in node_ids}

    for target, sources in dependencies.items():
        indegree[target] = len(sources)
        for source in sources:
            adjacency[source].append(target)

    ready = [node_id for node_id in node_ids if indegree[node_id] == 0]
    ordered: list[str] = []
    while ready:
        node_id = ready.pop(0)
        ordered.append(node_id)
        for target in adjacency[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)

    if len(ordered) != len(node_ids):
        raise ValidationException("Workflow definition contains a cycle")

    nodes_by_id = {_node_id(node): node for node in nodes}

    return [
        node_id
        for node_id in ordered
        if _is_tool_node(nodes_by_id[node_id])
    ]


def _required_workflow_inputs(definition: dict[str, Any]) -> set[str]:
    required_inputs: set[str] = set()
    for node in _workflow_nodes(definition):
        for source in (node.get("semantic_inputs") or {}).values():
            if not isinstance(source, str) or not source.startswith("workflow_input:"):
                continue
            semantic_type = source.split(":", 1)[1]
            if semantic_type:
                required_inputs.add(normalize_semantic_type(semantic_type))
    return required_inputs


async def _validate_input_files(
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


def _initial_node_states(definition: dict[str, Any], execution_order: list[str]) -> dict[str, Any]:
    nodes_by_id = _nodes_by_id(definition)
    return {
        node_id: {
            "status": "pending",
            "tool_slug": nodes_by_id[node_id].get("tool_slug"),
            "tool_id": nodes_by_id[node_id].get("tool_id"),
            "tool_version": nodes_by_id[node_id].get("tool_version"),
            "semantic_inputs": dict(nodes_by_id[node_id].get("semantic_inputs") or {}),
            "params": dict(nodes_by_id[node_id].get("params") or {}),
        }
        for node_id in execution_order
    }


def _dependency_tool_node_ids(definition: dict[str, Any], node_id: str) -> set[str]:
    nodes_by_id = _nodes_by_id(definition)
    dependencies = _workflow_dependency_map(definition)
    return {
        source
        for source in dependencies.get(node_id, set())
        if _is_tool_node(nodes_by_id.get(source))
    }


def _dependencies_satisfied(
    *,
    definition: dict[str, Any],
    node_states: dict[str, Any],
    node_id: str,
) -> bool:
    return all(
        (node_states.get(dependency_id) or {}).get("status") == "success"
        for dependency_id in _dependency_tool_node_ids(definition, node_id)
    )


async def _load_available_workflow_tool(
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


async def _resolve_node_input_files(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    node_id: str,
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
            source_node_id, source_semantic_type = parts[1], normalize_semantic_type(parts[2])
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


async def _schedule_workflow_node(
    db: AsyncSession,
    *,
    current_user: User,
    run: WorkflowRun,
    node_id: str,
    node: dict[str, Any],
    node_states: dict[str, Any],
) -> bool:
    input_file_ids = await _resolve_node_input_files(
        db,
        run=run,
        node_id=node_id,
        node=node,
        node_states=node_states,
    )
    if input_file_ids is None:
        return False

    tool = await _load_available_workflow_tool(db, node=node)
    node_params = dict(node.get("params") or {})
    task = await create_and_schedule_tool_task(
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
            "task_id": task.id,
            "input_file_ids": input_file_ids,
            "params": node_params,
            "started_at": _utcnow_iso(),
        }
    )
    node_states[node_id] = state
    return True


async def start_ready_workflow_nodes(
    db: AsyncSession,
    *,
    current_user: User,
    run: WorkflowRun,
) -> int:
    definition = dict(run.definition or {})
    node_states = dict(run.node_states or {})
    nodes_by_id = _nodes_by_id(definition)
    scheduled_count = 0

    for node_id in run.execution_order or []:
        state = dict(node_states.get(node_id) or {})
        if state.get("status") not in {None, "pending", "ready"}:
            continue
        if not _dependencies_satisfied(
            definition=definition,
            node_states=node_states,
            node_id=node_id,
        ):
            continue
        if await _schedule_workflow_node(
            db,
            current_user=current_user,
            run=run,
            node_id=node_id,
            node=nodes_by_id[node_id],
            node_states=node_states,
        ):
            scheduled_count += 1

    run.node_states = node_states
    if scheduled_count > 0:
        run.status = "waiting_task"
        run.started_at = run.started_at or _utcnow()
    elif run.execution_order and all(
        (node_states.get(node_id) or {}).get("status") == "success"
        for node_id in run.execution_order
    ):
        run.status = "success"
        run.finished_at = _utcnow()
    elif run.status == "pending":
        run.status = "pending"

    await db.commit()
    await db.refresh(run)
    return scheduled_count


async def _load_template_for_user(
    db: AsyncSession,
    *,
    template_id: str,
    current_user: User,
) -> WorkflowTemplate:
    result = await db.execute(
        select(WorkflowTemplate)
        .options(selectinload(WorkflowTemplate.runs))
        .where(WorkflowTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundException("Workflow template not found")
    if template.owner_id != current_user.id and not template.is_public and current_user.role != "admin":
        raise ForbiddenException("No permission to access workflow template")
    return template


async def _load_run_for_user(
    db: AsyncSession,
    *,
    run_id: str,
    current_user: User,
) -> WorkflowRun:
    result = await db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise NotFoundException("Workflow run not found")
    if run.owner_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException("No permission to access workflow run")
    return run


async def _load_task_output_files(
    db: AsyncSession,
    file_ids: list[str],
) -> list[dict[str, Any]]:
    if not file_ids:
        return []

    result = await db.execute(select(FileModel).where(FileModel.id.in_(file_ids)))
    files_by_id = {file.id: file for file in result.scalars().all()}
    output_files: list[dict[str, Any]] = []

    for file_id in file_ids:
        file_record = files_by_id.get(str(file_id))
        if not file_record:
            continue
        output_files.append(
            {
                "id": file_record.id,
                "filename": file_record.filename,
                "original_name": (file_record.file_meta or {}).get("original_name"),
                "content_type": file_record.content_type,
                "url": _file_download_url(file_record.id),
                "path": file_record.storage_path,
            }
        )

    return output_files


def _required_outputs_present(
    *,
    capability: Any,
    semantic_outputs: dict[str, dict[str, Any]],
) -> bool:
    return all(
        output.semantic_type in semantic_outputs
        for output in capability.outputs
        if output.required
    )


async def _annotate_semantic_output_files(
    db: AsyncSession,
    *,
    semantic_outputs: dict[str, dict[str, Any]],
) -> None:
    semantic_type_by_file_id = {
        str(value["file_id"]): semantic_type
        for semantic_type, value in semantic_outputs.items()
        if value.get("source") == "output_files" and value.get("file_id")
    }
    if not semantic_type_by_file_id:
        return

    result = await db.execute(
        select(FileModel).where(FileModel.id.in_(list(semantic_type_by_file_id.keys())))
    )
    for file_record in result.scalars().all():
        file_meta = dict(file_record.file_meta or {})
        file_meta["semantic_type"] = semantic_type_by_file_id[file_record.id]
        file_meta["semantic_source"] = "workflow_output"
        file_record.file_meta = file_meta
        db.add(file_record)


async def create_workflow_template(
    db: AsyncSession,
    *,
    current_user: User,
    data: WorkflowTemplateCreate,
) -> WorkflowTemplate:
    _validate_workflow_definition(data.definition)
    template = WorkflowTemplate(
        owner_id=current_user.id,
        name=data.name,
        description=data.description,
        definition=data.definition,
        is_public=data.is_public,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def list_workflow_templates(
    db: AsyncSession,
    *,
    current_user: User,
) -> list[WorkflowTemplate]:
    query = select(WorkflowTemplate).order_by(WorkflowTemplate.updated_at.desc())
    if current_user.role != "admin":
        query = query.where(
            (WorkflowTemplate.owner_id == current_user.id) | WorkflowTemplate.is_public.is_(True)
        )
    result = await db.execute(query)
    return list(result.scalars().all())


async def list_workflow_runs(
    db: AsyncSession,
    *,
    current_user: User,
    template_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[WorkflowRun], int]:
    query = select(WorkflowRun).where(WorkflowRun.owner_id == current_user.id)
    if template_id:
        query = query.where(WorkflowRun.template_id == template_id)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0
    result = await db.execute(
        query
        .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def get_workflow_template(
    db: AsyncSession,
    *,
    current_user: User,
    template_id: str,
) -> WorkflowTemplate:
    return await _load_template_for_user(db, template_id=template_id, current_user=current_user)


async def get_workflow_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
) -> WorkflowRun:
    return await _load_run_for_user(db, run_id=run_id, current_user=current_user)


async def update_workflow_template(
    db: AsyncSession,
    *,
    current_user: User,
    template_id: str,
    data: WorkflowTemplateUpdate,
) -> WorkflowTemplate:
    template = await _load_template_for_user(db, template_id=template_id, current_user=current_user)
    if template.owner_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException("No permission to update workflow template")
    if data.name is not None:
        template.name = data.name
    if data.description is not None:
        template.description = data.description
    if data.definition is not None:
        _validate_workflow_definition(data.definition)
        template.definition = data.definition
        template.version += 1
    if data.is_public is not None:
        template.is_public = data.is_public
    if data.status is not None:
        template.status = data.status
    await db.commit()
    await db.refresh(template)
    return template


async def duplicate_workflow_template(
    db: AsyncSession,
    *,
    current_user: User,
    template_id: str,
    data: WorkflowTemplateDuplicate,
) -> WorkflowTemplate:
    template = await _load_template_for_user(db, template_id=template_id, current_user=current_user)
    duplicated = WorkflowTemplate(
        owner_id=current_user.id,
        name=data.name or f"{template.name} Copy",
        description=template.description,
        definition=dict(template.definition or {}),
        is_public=False,
        version=1,
    )
    db.add(duplicated)
    await db.commit()
    await db.refresh(duplicated)
    return duplicated


async def delete_workflow_template(
    db: AsyncSession,
    *,
    current_user: User,
    template_id: str,
) -> dict[str, str]:
    template = await _load_template_for_user(db, template_id=template_id, current_user=current_user)
    if template.owner_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException("No permission to delete workflow template")
    deleted_id = template.id
    await db.delete(template)
    await db.commit()
    return {"id": deleted_id}


async def create_workflow_run(
    db: AsyncSession,
    *,
    current_user: User,
    template_id: str,
    data: WorkflowRunCreate,
) -> WorkflowRun:
    template = await _load_template_for_user(db, template_id=template_id, current_user=current_user)
    definition = dict(template.definition or {})
    execution_order = _validate_workflow_definition(definition)
    input_files = await _validate_input_files(
        db,
        current_user=current_user,
        input_files=data.input_files,
    )
    missing_inputs = sorted(_required_workflow_inputs(definition) - set(input_files.keys()))
    if missing_inputs:
        raise ValidationException(
            "Workflow run is missing required inputs: " + ", ".join(missing_inputs)
        )

    run = WorkflowRun(
        owner_id=current_user.id,
        template_id=template.id,
        name=data.name or template.name,
        status="pending",
        definition=definition,
        input_files=input_files,
        execution_order=execution_order,
        node_states=_initial_node_states(definition, execution_order),
        artifact_lineage={},
    )
    db.add(run)
    await db.flush()
    await start_ready_workflow_nodes(db, current_user=current_user, run=run)
    return run


async def sync_workflow_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
) -> WorkflowRun:
    run = await _load_run_for_user(db, run_id=run_id, current_user=current_user)
    node_states = dict(run.node_states or {})
    artifact_lineage = dict(run.artifact_lineage or {})

    for node_id in run.execution_order or []:
        state = dict(node_states.get(node_id) or {})
        if state.get("status") != "waiting_task":
            continue

        task_id = state.get("task_id")
        if not task_id:
            state["status"] = "failure"
            state["error_message"] = "Workflow node is waiting without a task id"
            state["finished_at"] = _utcnow_iso()
            node_states[node_id] = state
            run.status = "failure"
            run.error_message = state["error_message"]
            run.finished_at = _utcnow()
            continue

        task_result = await db.execute(
            select(Task)
            .options(selectinload(Task.outputs))
            .where(Task.id == str(task_id))
        )
        task = task_result.scalar_one_or_none()
        if not task:
            state["status"] = "failure"
            state["error_message"] = "Workflow node task not found"
            state["finished_at"] = _utcnow_iso()
            node_states[node_id] = state
            run.status = "failure"
            run.error_message = state["error_message"]
            run.finished_at = _utcnow()
            continue

        if task.status in {TaskStatus.PENDING.value, TaskStatus.RUNNING.value}:
            continue

        if task.status in {TaskStatus.FAILURE.value, TaskStatus.CANCELED.value}:
            state["status"] = "failure"
            state["error_message"] = task.error_message or "Workflow node task failed"
            state["finished_at"] = _utcnow_iso()
            node_states[node_id] = state
            run.status = "failure"
            run.error_message = state["error_message"]
            run.finished_at = _utcnow()
            continue

        file_ids = [str(file_id) for file_id in (task.outputs.file_ids if task.outputs else [])]
        output_files = await _load_task_output_files(db, file_ids)
        output_data = task.outputs.result if task.outputs else None
        capability = await load_tool_capability(db, str(state.get("tool_slug") or ""))
        semantic_outputs = extract_semantic_outputs(
            capability=capability,
            task_output_files=output_files,
            output_data=output_data,
        )
        if not _required_outputs_present(capability=capability, semantic_outputs=semantic_outputs):
            state["status"] = "failure"
            state["error_message"] = "Workflow node task succeeded but required semantic outputs are missing"
            state["finished_at"] = _utcnow_iso()
            node_states[node_id] = state
            run.status = "failure"
            run.error_message = state["error_message"]
            run.finished_at = _utcnow()
            continue

        state["status"] = "success"
        state["semantic_outputs"] = semantic_outputs
        await _annotate_semantic_output_files(db, semantic_outputs=semantic_outputs)
        state["output_file_ids"] = [
            str(value["file_id"])
            for value in semantic_outputs.values()
            if value.get("source") == "output_files" and value.get("file_id")
        ]
        state["finished_at"] = _utcnow_iso()
        node_states[node_id] = state
        artifact_lineage[node_id] = semantic_outputs

    run.node_states = node_states
    run.artifact_lineage = artifact_lineage
    if run.status != "failure":
        await start_ready_workflow_nodes(db, current_user=current_user, run=run)
        run = await _load_run_for_user(db, run_id=run_id, current_user=current_user)
    else:
        await db.commit()
        await db.refresh(run)
    return run
