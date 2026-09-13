"""Workflow run persistence and synchronization service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.aidd.outputs import extract_semantic_outputs
from app.agents.aidd.registry import load_tool_capability
from app.common.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.common.time import utcnow, utcnow_iso
from app.models.tasks import Task, TaskStatus
from app.models.users import User
from app.models.workflows import WorkflowDefinition, WorkflowRun
from app.schemas.workflows import WorkflowRunCreate
from app.services.project_access import load_project_membership
from app.services.project_migration import ensure_migration_project_for_owner
from app.services.standard_input_slots import tool_accepts_standard_input_bindings
from app.tasks.cancellation import cancel_platform_task
from app.services.workflow_artifacts import (
    annotate_semantic_output_files,
    describe_missing_required_standard_artifacts,
    describe_missing_required_outputs,
    extract_standard_artifacts,
    format_missing_required_standard_artifacts_error,
    format_missing_required_outputs_error,
    load_task_output_files,
    required_outputs_present,
    standard_artifact_file_ids,
)
from app.services.workflow_cancellation import mark_active_workflow_state_canceled
from app.services.workflow_inputs import validate_input_files
from app.services.workflow_loop_scheduler import reconcile_loop_body
from app.services.workflow_map_scheduler import reconcile_map_sub_tasks
from app.services.workflow_node_states import initial_node_states
from app.services.workflow_run_access import ensure_run_operation_access, is_admin
from app.services.workflow_scheduler import start_ready_workflow_nodes
from app.services.workflow_tool_lookup import load_available_workflow_tool
from app.services.workflow_validation import (
    is_loop_node,
    is_map_node,
    is_tool_node,
    nodes_by_id,
    required_workflow_inputs,
    validate_workflow_definition,
    workflow_nodes,
)


WORKFLOW_RUN_TERMINAL_STATUSES = {"success", "failure", "canceled"}


async def materialize_workflow_run_definition(
    db: AsyncSession,
    *,
    definition: dict[str, Any],
) -> dict[str, Any]:
    materialized_definition = {
        **definition,
        "nodes": [dict(node) for node in workflow_nodes(definition)],
        "edges": list(definition.get("edges") or []),
    }
    for node in materialized_definition["nodes"]:
        if not is_tool_node(node):
            continue
        tool = await load_available_workflow_tool(db, node=node)
        node["tool_id"] = tool.id
        node["tool_slug"] = tool.slug
        node["tool_version"] = {
            "id": tool.current_version_id,
            "version": tool.current_version.version if tool.current_version else None,
        }
    return materialized_definition


async def load_run_for_user(
    db: AsyncSession,
    *,
    run_id: str,
    current_user: User,
) -> WorkflowRun:
    result = await db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise NotFoundException("Workflow run not found")
    if run.project_id:
        if not is_admin(current_user):
            await load_project_membership(
                db,
                project_id=run.project_id,
                user_id=current_user.id,
            )
        return run
    if run.owner_id != current_user.id and not is_admin(current_user):
        raise ForbiddenException("No permission to access workflow run")
    return run


async def load_definition_for_run(
    db: AsyncSession,
    *,
    workflow_definition_id: str,
    current_user: User,
) -> WorkflowDefinition:
    result = await db.execute(
        select(WorkflowDefinition).where(WorkflowDefinition.id == workflow_definition_id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise NotFoundException("Workflow definition not found")
    if workflow.project_id:
        if not is_admin(current_user):
            await load_project_membership(
                db,
                project_id=workflow.project_id,
                user_id=current_user.id,
            )
        return workflow
    if workflow.user_id != current_user.id and not is_admin(current_user):
        raise NotFoundException("Workflow definition not found")
    return workflow


async def list_workflow_runs(
    db: AsyncSession,
    *,
    current_user: User,
    workflow_definition_id: str | None = None,
    project_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[WorkflowRun], int]:
    if workflow_definition_id and not project_id:
        workflow = await load_definition_for_run(
            db,
            workflow_definition_id=workflow_definition_id,
            current_user=current_user,
        )
        project_id = workflow.project_id
    if project_id:
        if not is_admin(current_user):
            await load_project_membership(
                db,
                project_id=project_id,
                user_id=current_user.id,
            )
        query = select(WorkflowRun).where(WorkflowRun.project_id == project_id)
    else:
        query = select(WorkflowRun).where(WorkflowRun.owner_id == current_user.id)
    if workflow_definition_id:
        query = query.where(WorkflowRun.workflow_definition_id == workflow_definition_id)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0
    result = await db.execute(
        query
        .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def get_workflow_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
) -> WorkflowRun:
    return await load_run_for_user(db, run_id=run_id, current_user=current_user)


async def create_workflow_run(
    db: AsyncSession,
    *,
    current_user: User,
    workflow_definition_id: str,
    data: WorkflowRunCreate,
    schedule_task_fn,
) -> WorkflowRun:
    workflow = await load_definition_for_run(
        db,
        workflow_definition_id=workflow_definition_id,
        current_user=current_user,
    )
    definition = {
        "nodes": [dict(node) for node in (workflow.nodes or [])],
        "edges": [dict(edge) for edge in (workflow.edges or [])],
        "selected_tool_by_node": dict(workflow.selected_tool_by_node or {}),
        "artifact_bindings_by_node": dict(workflow.artifact_bindings_by_node or {}),
    }
    execution_order = validate_workflow_definition(definition)
    materialized_definition = await materialize_workflow_run_definition(
        db,
        definition=definition,
    )
    input_files = await validate_input_files(
        db,
        current_user=current_user,
        input_files=data.input_files,
    )
    missing_inputs = sorted(required_workflow_inputs(definition) - set(input_files.keys()))
    if missing_inputs:
        raise ValidationException(
            "Workflow run is missing required inputs: " + ", ".join(missing_inputs)
        )

    project_id = workflow.project_id
    if project_id is None and await _workflow_requires_standard_binding_project(
        db,
        materialized_definition,
    ):
        project = await ensure_migration_project_for_owner(db, current_user)
        project_id = str(project.id)

    run = WorkflowRun(
        owner_id=current_user.id,
        workflow_definition_id=workflow.id,
        project_id=project_id,
        name=data.name or workflow.name,
        status="pending",
        definition=materialized_definition,
        input_files=input_files,
        execution_order=execution_order,
        node_states=initial_node_states(materialized_definition, execution_order),
        artifact_lineage={},
    )
    db.add(run)
    await db.flush()
    await start_ready_workflow_nodes(
        db,
        current_user=current_user,
        run=run,
        schedule_task_fn=schedule_task_fn,
    )
    return run


async def _workflow_requires_standard_binding_project(
    db: AsyncSession,
    definition: dict[str, Any],
) -> bool:
    for node in workflow_nodes(definition):
        if not is_tool_node(node):
            continue
        tool = await load_available_workflow_tool(db, node=node)
        config = getattr(getattr(tool, "current_version", None), "config", None)
        if tool_accepts_standard_input_bindings(config if isinstance(config, dict) else {}):
            return True
    return False


async def sync_workflow_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
    schedule_task_fn,
) -> WorkflowRun:
    run = await load_run_for_user(db, run_id=run_id, current_user=current_user)
    node_states = dict(run.node_states or {})
    artifact_lineage = dict(run.artifact_lineage or {})

    for node_id in run.execution_order or []:
        state = dict(node_states.get(node_id) or {})
        if state.get("status") != "waiting_task":
            continue

        # Map nodes have sub-tasks; delegate to reconcile_map_sub_tasks
        definition = dict(run.definition or {})
        indexed_nodes = nodes_by_id(definition)
        node = indexed_nodes.get(node_id)
        if is_map_node(node) and state.get("sub_tasks"):
            await reconcile_map_sub_tasks(
                db,
                node_id=node_id,
                state=state,
                node_states=node_states,
                run=run,
            )
            if state.get("status") not in ("waiting_task",):
                continue

        # Loop nodes have body sub-tasks; delegate to reconcile_loop_body
        if is_loop_node(node) and state.get("loop_body_states"):
            await reconcile_loop_body(
                db,
                node_id=node_id,
                node=node,
                state=state,
                node_states=node_states,
                run=run,
            )
            if state.get("status") not in ("waiting_task",):
                continue

        task_id = state.get("task_id")
        if not task_id:
            state["status"] = "failure"
            state["error_message"] = "Workflow node is waiting without a task id"
            state["finished_at"] = utcnow_iso()
            node_states[node_id] = state
            run.status = "failure"
            run.error_message = state["error_message"]
            run.finished_at = utcnow()
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
            state["finished_at"] = utcnow_iso()
            node_states[node_id] = state
            run.status = "failure"
            run.error_message = state["error_message"]
            run.finished_at = utcnow()
            continue

        if task.status in {TaskStatus.PENDING.value, TaskStatus.RUNNING.value}:
            continue

        if task.status in {TaskStatus.FAILURE.value, TaskStatus.CANCELED.value}:
            state["status"] = "failure"
            state["error_message"] = task.error_message or "Workflow node task failed"
            state["finished_at"] = utcnow_iso()
            node_states[node_id] = state
            run.status = "failure"
            run.error_message = state["error_message"]
            run.finished_at = utcnow()
            continue

        if run.project_id is None:
            task_project_id = _task_project_id(task)
            if task_project_id:
                run.project_id = task_project_id

        file_ids = [str(file_id) for file_id in (task.outputs.file_ids if task.outputs else [])]
        output_files = await load_task_output_files(db, file_ids)
        output_data = task.outputs.result if task.outputs else None
        capability = await load_tool_capability(db, str(state.get("tool_slug") or ""))
        semantic_outputs = extract_semantic_outputs(
            capability=capability,
            task_output_files=output_files,
            output_data=output_data,
        )
        standard_artifacts = extract_standard_artifacts(output_data)
        declared_artifact_outputs = list(state.get("artifact_outputs") or [])
        missing_artifacts = describe_missing_required_standard_artifacts(
            declared_outputs=declared_artifact_outputs,
            standard_artifacts=standard_artifacts,
        )
        standard_artifacts_satisfy_required = (
            _has_required_declared_standard_outputs(declared_artifact_outputs)
            and not missing_artifacts
        )
        if (
            not required_outputs_present(capability=capability, semantic_outputs=semantic_outputs)
            and not standard_artifacts_satisfy_required
        ):
            missing_outputs = describe_missing_required_outputs(
                capability=capability,
                semantic_outputs=semantic_outputs,
            )
            state["status"] = "failure"
            state["missing_outputs"] = missing_outputs
            state["error_message"] = format_missing_required_outputs_error(missing_outputs)
            state["finished_at"] = utcnow_iso()
            node_states[node_id] = state
            run.status = "failure"
            run.error_message = state["error_message"]
            run.finished_at = utcnow()
            continue

        if missing_artifacts:
            state["status"] = "failure"
            state["missing_outputs"] = missing_artifacts
            state["error_message"] = format_missing_required_standard_artifacts_error(
                missing_artifacts
            )
            state["finished_at"] = utcnow_iso()
            node_states[node_id] = state
            run.status = "failure"
            run.error_message = state["error_message"]
            run.finished_at = utcnow()
            continue

        state["status"] = "success"
        state["semantic_outputs"] = semantic_outputs
        state["standard_artifacts"] = standard_artifacts
        state["missing_outputs"] = []
        await annotate_semantic_output_files(db, semantic_outputs=semantic_outputs)
        output_file_ids = [
            str(value["file_id"])
            for value in semantic_outputs.values()
            if value.get("source") == "output_files" and value.get("file_id")
        ]
        for declaration in declared_artifact_outputs:
            if not isinstance(declaration, dict) or not declaration.get("name"):
                continue
            output_file_ids.extend(
                standard_artifact_file_ids(standard_artifacts, str(declaration["name"]))
            )
        state["output_file_ids"] = list(dict.fromkeys(output_file_ids))
        state["finished_at"] = utcnow_iso()
        node_states[node_id] = state
        artifact_lineage[node_id] = dict(semantic_outputs)
        if standard_artifacts:
            artifact_lineage[node_id]["standard_artifacts"] = standard_artifacts

    run.node_states = node_states
    run.artifact_lineage = artifact_lineage
    if run.status != "failure":
        await start_ready_workflow_nodes(
            db,
            current_user=current_user,
            run=run,
            schedule_task_fn=schedule_task_fn,
        )
        run = await load_run_for_user(db, run_id=run_id, current_user=current_user)
    else:
        await db.commit()
        await db.refresh(run)
    return run


def _has_required_declared_standard_outputs(declared_outputs: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(declaration, dict)
        and bool(declaration.get("name"))
        and declaration.get("required", True) is not False
        for declaration in declared_outputs
    )


def _task_project_id(task: Task) -> str | None:
    data = task.extra_data if isinstance(task.extra_data, dict) else {}
    project_id = data.get("project_id")
    return str(project_id) if project_id else None


async def cancel_workflow_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
) -> WorkflowRun:
    run = await load_run_for_user(db, run_id=run_id, current_user=current_user)
    await ensure_run_operation_access(db, run=run, current_user=current_user)

    if run.status == "canceled":
        return run
    if run.status in WORKFLOW_RUN_TERMINAL_STATUSES:
        raise ValidationException(f"Cannot cancel terminal workflow run: {run.status}")

    node_states = dict(run.node_states or {})
    finished_at = utcnow_iso()
    task_ids: list[str] = []

    for node_id, raw_state in node_states.items():
        state = dict(raw_state or {})
        task_ids.extend(mark_active_workflow_state_canceled(state, finished_at=finished_at))
        node_states[node_id] = state

    if task_ids:
        result = await db.execute(select(Task).where(Task.id.in_(task_ids)))
        for task in result.scalars().all():
            await cancel_platform_task(db, task=task, current_user=current_user)

    run.status = "canceled"
    run.node_states = node_states
    run.finished_at = utcnow()
    run.error_message = None
    await db.commit()
    await db.refresh(run)
    return run


async def retry_workflow_run_node(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
    node_id: str,
    schedule_task_fn,
) -> WorkflowRun:
    run = await load_run_for_user(db, run_id=run_id, current_user=current_user)
    await ensure_run_operation_access(db, run=run, current_user=current_user)
    if run.status == "canceled":
        raise ValidationException("Cannot retry a canceled workflow run")

    definition = dict(run.definition or {})
    indexed_nodes = nodes_by_id(definition)
    if node_id not in indexed_nodes:
        raise NotFoundException("Workflow node not found")

    node_states = dict(run.node_states or {})
    current_state = dict(node_states.get(node_id) or {})
    if current_state.get("status") != "failure":
        raise ValidationException("Only failed workflow nodes can be retried")

    initial_states = initial_node_states(definition, list(run.execution_order or []))
    retry_state = dict(initial_states.get(node_id) or {"status": "pending"})
    node_states[node_id] = retry_state

    artifact_lineage = dict(run.artifact_lineage or {})
    artifact_lineage.pop(node_id, None)

    run.status = "pending"
    run.error_message = None
    run.finished_at = None
    run.node_states = node_states
    run.artifact_lineage = artifact_lineage

    await start_ready_workflow_nodes(
        db,
        current_user=current_user,
        run=run,
        schedule_task_fn=schedule_task_fn,
    )
    return await load_run_for_user(db, run_id=run_id, current_user=current_user)
