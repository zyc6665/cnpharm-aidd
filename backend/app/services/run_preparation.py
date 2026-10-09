"""Prepare tool runs from parameters, files, and standard Artifact bindings."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.files import File as FileModel
from app.services.artifact_binding_resolver import resolve_artifact_binding
from app.services.run_input_validation import (
    dedupe_ordered,
    input_bindings_requiring_validation,
    require_existing_file_id,
    validate_standard_input_bindings,
)
from app.services.run_input_normalization import normalize_string_mapping
from app.services.run_legacy_projection import (
    existing_input_file_fields,
    project_file_to_legacy_params,
    tool_version_config,
)
from app.services.standard_input_slots import (
    artifact_input_slots_by_name,
    artifact_input_slots_for_run,
    tool_accepts_standard_input_bindings,
)
from app.services.tool_contracts import build_tool_contract
from app.services.workflow_run_input_sources import (
    WorkflowInputSources,
    resolve_workflow_input_sources,
)


RunSurface = Literal["tool_detail", "standalone_node", "workflow_node", "agent_plan"]


@dataclass(frozen=True)
class RunContext:
    """Context shared by all run surfaces before a task is created."""

    surface: RunSurface
    user_id: str
    project_id: str | None = None
    workflow_run_id: str | None = None
    workflow_definition_id: str | None = None
    workflow_node_id: str | None = None


@dataclass(frozen=True)
class RunPreparationInput:
    """Raw run request values before platform preparation."""

    tool: Any
    tool_version: Any
    context: RunContext
    params: dict[str, Any]
    file_ids: list[str]
    input_bindings: dict[str, str]
    standard_input_uploads: dict[str, str]
    workflow_node: dict[str, Any] | None = None


@dataclass(frozen=True)
class PreparedRun:
    """Prepared task inputs and readiness decisions."""

    ready: bool
    project_id: str | None
    params: dict[str, Any]
    file_ids: list[str]
    input_bindings: dict[str, str]
    standard_input_uploads: dict[str, str]
    binding_decisions: dict[str, dict[str, Any]]
    blocked_reason: str | None = None


async def prepare_run(db: AsyncSession, *, input: RunPreparationInput) -> PreparedRun:
    """Normalize and validate inputs for a tool task without creating the task."""
    params = dict(input.params or {})
    file_ids = list(input.file_ids or [])
    project_id = input.context.project_id
    file_ids = await _include_legacy_input_files(
        db,
        params=params,
        file_ids=file_ids,
        project_id=project_id,
    )
    input_bindings = normalize_string_mapping(input.input_bindings)
    standard_input_uploads = normalize_string_mapping(input.standard_input_uploads)

    for file_id in dedupe_ordered(file_ids):
        await require_existing_file_id(
            db,
            file_id=file_id,
            project_id=project_id,
        )

    contract = build_tool_contract(input.tool)
    artifact_inputs = artifact_input_slots_for_run(contract, input.workflow_node)
    artifact_inputs_by_name = artifact_input_slots_by_name(artifact_inputs)
    accepts_standard_bindings = tool_accepts_standard_input_bindings(
        tool_version_config(input.tool_version)
    )
    input_bindings_to_validate = input_bindings_requiring_validation(
        input_bindings,
        artifact_inputs_by_name,
        accepts_standard_bindings=accepts_standard_bindings,
        surface=input.context.surface,
    )
    await validate_standard_input_bindings(
        db,
        project_id=project_id,
        input_bindings=input_bindings_to_validate,
    )
    binding_decisions: dict[str, dict[str, Any]] = {}
    ready = True
    blocked_reason: str | None = None
    legacy_projection_fields = existing_input_file_fields(params)

    for slot_name, version_id in input_bindings.items():
        slot = artifact_inputs_by_name.get(slot_name)
        if not slot or accepts_standard_bindings:
            continue

        decision = await resolve_artifact_binding(
            db,
            input_slot=slot,
            candidate_artifact_version_id=version_id,
        )
        decision_dict = asdict(decision)
        binding_decisions[slot_name] = decision_dict
        if decision.status != "ready":
            ready = False
            blocked_reason = blocked_reason or decision.reason or decision.status
            continue
        if not decision.selected_file_id or accepts_standard_bindings:
            continue

        await require_existing_file_id(
            db,
            file_id=decision.selected_file_id,
            project_id=project_id,
        )
        file_ids.append(decision.selected_file_id)
        await project_file_to_legacy_params(
            db,
            tool_version=input.tool_version,
            input_slot=slot,
            file_id=decision.selected_file_id,
            params=params,
            used_fields=legacy_projection_fields,
        )

    if ready:
        for slot_name, file_id in standard_input_uploads.items():
            slot = artifact_inputs_by_name.get(slot_name)
            if not slot:
                continue
            await require_existing_file_id(db, file_id=file_id, project_id=project_id)
            file_ids.append(file_id)
            if not accepts_standard_bindings:
                await project_file_to_legacy_params(
                    db,
                    tool_version=input.tool_version,
                    input_slot=slot,
                    file_id=file_id,
                    params=params,
                    used_fields=legacy_projection_fields,
                )
    task_input_bindings = dict(input_bindings) if accepts_standard_bindings else {}

    return PreparedRun(
        ready=ready,
        project_id=project_id,
        params=params,
        file_ids=dedupe_ordered(file_ids) if ready else [],
        input_bindings=task_input_bindings,
        standard_input_uploads=standard_input_uploads,
        binding_decisions=binding_decisions,
        blocked_reason=blocked_reason,
    )


async def _include_legacy_input_files(
    db: AsyncSession,
    *,
    params: dict[str, Any],
    file_ids: list[str],
    project_id: str | None,
) -> list[str]:
    """Resolve legacy input_files file IDs into the task's staged file list."""
    input_files = params.get("input_files")
    if not isinstance(input_files, dict):
        return file_ids

    referenced_ids = [
        str(value)
        for value in input_files.values()
        if value and _looks_like_file_id(value)
    ]
    if not referenced_ids:
        return file_ids

    query = select(FileModel.id, FileModel.filename).where(
        FileModel.id.in_(referenced_ids)
    )
    if project_id:
        query = query.where(
            (FileModel.project_id == project_id) | (FileModel.project_id.is_(None))
        )
    result = await db.execute(query)
    file_records = {
        str(file_id): str(filename)
        for file_id, filename in result.all()
    }
    params["input_files"] = {
        field: (
            f"input/{file_records[str(value)]}"
            if str(value) in file_records
            else value
        )
        for field, value in input_files.items()
    }
    return dedupe_ordered(
        [*file_ids, *[file_id for file_id in referenced_ids if file_id in file_records]]
    )


def _looks_like_file_id(value: Any) -> bool:
    """Avoid treating legacy relative paths and ordinary values as file IDs."""
    candidate = str(value).strip()
    return "/" not in candidate and "\\" not in candidate


async def prepare_workflow_node_run(
    db: AsyncSession,
    *,
    run: Any,
    node_id: str,
    node: dict[str, Any],
    node_states: dict[str, Any],
    tool: Any,
    current_user: Any,
    params: dict[str, Any],
) -> PreparedRun | None:
    """Prepare a workflow tool invocation, returning None while upstream is pending."""
    sources = await resolve_workflow_input_sources(
        db,
        run=run,
        node=node,
        node_states=node_states,
    )
    if sources is None:
        return None
    if sources.binding_decisions:
        return PreparedRun(
            ready=False,
            project_id=getattr(run, "project_id", None),
            params=dict(params),
            file_ids=[],
            input_bindings={},
            standard_input_uploads={},
            binding_decisions=sources.binding_decisions,
            blocked_reason=_first_blocking_binding_reason(sources.binding_decisions),
        )

    preparation_input = RunPreparationInput(
        tool=tool,
        tool_version=getattr(tool, "current_version", None),
        context=RunContext(
            surface="workflow_node",
            user_id=str(getattr(current_user, "id", "")),
            project_id=getattr(run, "project_id", None),
            workflow_run_id=str(getattr(run, "id", "")),
            workflow_definition_id=str(getattr(run, "workflow_definition_id", "")),
            workflow_node_id=str(node_id),
        ),
        params=dict(params),
        file_ids=sources.file_ids,
        input_bindings=sources.input_bindings,
        standard_input_uploads=sources.standard_input_uploads,
        workflow_node=node,
    )
    prepared = await prepare_run(db, input=preparation_input)
    if _can_fallback_to_workflow_files(prepared, sources):
        fallback_input_bindings = {
            slot_name: version_id
            for slot_name, version_id in preparation_input.input_bindings.items()
            if slot_name not in sources.legacy_file_bindings
        }
        fallback = await prepare_run(
            db,
            input=replace(
                preparation_input,
                input_bindings=fallback_input_bindings,
            ),
        )
        if fallback.ready:
            prepared = fallback
    if not prepared.ready:
        return prepared

    next_params = dict(prepared.params)
    if tool_version_config(getattr(tool, "current_version", None)).get("type") == "builtin":
        for standard_type, file_id in sources.semantic_file_bindings.items():
            await project_file_to_legacy_params(
                db,
                tool_version=getattr(tool, "current_version", None),
                input_slot={"name": standard_type, "type": standard_type},
                file_id=file_id,
                params=next_params,
            )
    if not prepared.input_bindings:
        for slot_name, file_id in sources.legacy_file_bindings.items():
            slot = sources.artifact_slots.get(slot_name) or {"name": slot_name}
            await project_file_to_legacy_params(
                db,
                tool_version=getattr(tool, "current_version", None),
                input_slot=slot,
                file_id=file_id,
                params=next_params,
            )

    return replace(prepared, params=next_params)


def _first_blocking_binding_reason(decisions: dict[str, dict[str, Any]]) -> str | None:
    for decision in decisions.values():
        if not isinstance(decision, dict) or decision.get("status") == "ready":
            continue
        return str(
            decision.get("reason")
            or decision.get("status")
            or "Artifact binding blocked"
        )
    return None


def _can_fallback_to_workflow_files(
    prepared: PreparedRun,
    sources: WorkflowInputSources,
) -> bool:
    if prepared.ready or not sources.legacy_file_bindings:
        return False

    fallbackable_slots = 0
    for slot_name, decision in prepared.binding_decisions.items():
        if not isinstance(decision, dict) or decision.get("status") == "ready":
            continue
        if slot_name not in sources.legacy_file_bindings:
            return False
        reason = str(decision.get("reason") or "")
        if (
            decision.get("status") != "invalid"
            or not reason.startswith("ArtifactVersion ")
            or not reason.endswith(" was not found.")
        ):
            return False
        fallbackable_slots += 1

    return fallbackable_slots > 0
