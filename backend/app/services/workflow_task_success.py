"""Workflow task success state application."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.aidd.outputs import extract_semantic_outputs
from app.agents.aidd.registry import load_tool_capability
from app.common.time import utcnow_iso
from app.models.tasks import Task
from app.models.workflows import WorkflowRun
from app.services.workflow_artifacts import (
    annotate_semantic_output_files,
    describe_missing_required_standard_artifacts,
    describe_missing_required_outputs,
    extract_standard_artifacts,
    format_missing_required_standard_artifacts_error,
    format_missing_required_outputs_error,
    load_task_output_files,
    required_outputs_present,
)
from app.services.workflow_run_failures import mark_workflow_node_failed
from app.services.workflow_task_outputs import (
    has_required_declared_standard_outputs,
    task_project_id,
    workflow_output_file_ids,
)


async def apply_successful_task_outputs(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    node_states: dict[str, Any],
    artifact_lineage: dict[str, Any],
    node_id: str,
    state: dict[str, Any],
    task: Task,
) -> None:
    if getattr(run, "project_id", None) is None:
        project_id = task_project_id(task)
        if project_id:
            run.project_id = project_id

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
        has_required_declared_standard_outputs(declared_artifact_outputs)
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
        mark_workflow_node_failed(
            run,
            node_states=node_states,
            node_id=node_id,
            state=state,
            error_message=format_missing_required_outputs_error(missing_outputs),
            missing_outputs=missing_outputs,
        )
        return

    if missing_artifacts:
        mark_workflow_node_failed(
            run,
            node_states=node_states,
            node_id=node_id,
            state=state,
            error_message=format_missing_required_standard_artifacts_error(missing_artifacts),
            missing_outputs=missing_artifacts,
        )
        return

    state["status"] = "success"
    state["semantic_outputs"] = semantic_outputs
    state["standard_artifacts"] = standard_artifacts
    state["missing_outputs"] = []
    await annotate_semantic_output_files(db, semantic_outputs=semantic_outputs)
    state["output_file_ids"] = workflow_output_file_ids(
        semantic_outputs=semantic_outputs,
        standard_artifacts=standard_artifacts,
        declared_artifact_outputs=declared_artifact_outputs,
    )
    state["finished_at"] = utcnow_iso()
    node_states[node_id] = state
    artifact_lineage[node_id] = dict(semantic_outputs)
    if standard_artifacts:
        artifact_lineage[node_id]["standard_artifacts"] = standard_artifacts
