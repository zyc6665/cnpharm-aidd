"""Workflow run persistence and synchronization service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ValidationException
from app.common.time import utcnow_iso
from app.models.tasks import Task
from app.models.users import User
from app.models.workflows import WorkflowRun
from app.schemas.workflows import WorkflowRunCreate
from app.services.project_migration import ensure_migration_project_for_owner
from app.tasks.cancellation import cancel_platform_task
from app.services.workflow_cancellation import mark_workflow_run_canceled
from app.services.workflow_inputs import validate_input_files
from app.services.workflow_loop_scheduler import reconcile_loop_body
from app.services.workflow_map_scheduler import reconcile_map_sub_tasks
from app.services.workflow_node_states import initial_node_states
from app.services.workflow_run_access import ensure_run_operation_access
from app.services.workflow_run_materialization import (
    materialize_workflow_run_definition,
    workflow_requires_standard_binding_project,
)
from app.services.workflow_run_queries import load_definition_for_run, load_run_for_user
from app.services.workflow_run_retry import prepare_workflow_node_retry
from app.services.workflow_scheduler import start_ready_workflow_nodes
from app.services.workflow_task_success import apply_successful_task_outputs
from app.services.workflow_validation import (
    is_loop_node,
    is_map_node,
    nodes_by_id,
    required_workflow_inputs,
    validate_workflow_definition,
)
from app.services.workflow_waiting_task import load_finished_workflow_node_task


WORKFLOW_RUN_TERMINAL_STATUSES = {"success", "failure", "canceled"}


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
        project_id=workflow.project_id,
    )
    missing_inputs = sorted(required_workflow_inputs(definition) - set(input_files.keys()))
    if missing_inputs:
        raise ValidationException(
            "Workflow run is missing required inputs: " + ", ".join(missing_inputs)
        )

    project_id = workflow.project_id
    if project_id is None and await workflow_requires_standard_binding_project(
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

        task = await load_finished_workflow_node_task(
            db,
            run=run,
            node_states=node_states,
            node_id=node_id,
            state=state,
        )
        if task is None:
            continue

        await apply_successful_task_outputs(
            db,
            run=run,
            node_states=node_states,
            artifact_lineage=artifact_lineage,
            node_id=node_id,
            state=state,
            task=task,
        )

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

    task_ids = mark_workflow_run_canceled(run, finished_at=utcnow_iso())

    if task_ids:
        result = await db.execute(select(Task).where(Task.id.in_(task_ids)))
        for task in result.scalars().all():
            await cancel_platform_task(db, task=task, current_user=current_user)

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
    prepare_workflow_node_retry(run, node_id=node_id)

    await start_ready_workflow_nodes(
        db,
        current_user=current_user,
        run=run,
        schedule_task_fn=schedule_task_fn,
    )
    return await load_run_for_user(db, run_id=run_id, current_user=current_user)
