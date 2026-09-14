"""Prepare tool runs from parameters, files, and standard Artifact bindings."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundException, ValidationException
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.files import File as FileModel
from app.services.artifact_binding_resolver import (
    ArtifactBindingDecision,
    resolve_artifact_binding,
)
from app.services.run_input_normalization import normalize_string_mapping
from app.services.run_legacy_projection import (
    existing_input_file_fields,
    project_file_to_legacy_params,
    tool_version_config,
)
from app.services.semantic_types import normalize_semantic_type
from app.services.standard_input_slots import (
    artifact_input_slots_by_name,
    artifact_input_slots_by_name_for_node,
    artifact_input_slots_for_run,
    tool_accepts_standard_input_bindings,
)
from app.services.tool_contracts import build_tool_contract
from app.services.workflow_artifacts import standard_artifact_file_ids


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
    input_bindings = normalize_string_mapping(input.input_bindings)
    standard_input_uploads = normalize_string_mapping(input.standard_input_uploads)
    project_id = input.context.project_id

    contract = build_tool_contract(input.tool)
    artifact_inputs = artifact_input_slots_for_run(contract, input.workflow_node)
    artifact_inputs_by_name = artifact_input_slots_by_name(artifact_inputs)
    accepts_standard_bindings = tool_accepts_standard_input_bindings(
        tool_version_config(input.tool_version)
    )
    input_bindings_to_validate = _input_bindings_requiring_validation(
        input_bindings,
        artifact_inputs_by_name,
        accepts_standard_bindings=accepts_standard_bindings,
        surface=input.context.surface,
    )
    await _validate_standard_input_bindings(
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
        if not slot or not _slot_needs_binding_resolution(slot):
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
            await _require_existing_file_id(db, file_id=file_id, project_id=project_id)
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
        file_ids=_dedupe_ordered(file_ids) if ready else [],
        input_bindings=task_input_bindings,
        standard_input_uploads=standard_input_uploads,
        binding_decisions=binding_decisions,
        blocked_reason=blocked_reason,
    )


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
    sources = await _resolve_workflow_input_sources(
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

    prepared = await prepare_run(
        db,
        input=RunPreparationInput(
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
        ),
    )
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


@dataclass(frozen=True)
class _WorkflowInputSources:
    file_ids: list[str]
    input_bindings: dict[str, str]
    standard_input_uploads: dict[str, str]
    binding_decisions: dict[str, dict[str, Any]]
    legacy_file_bindings: dict[str, str]
    semantic_file_bindings: dict[str, str]
    artifact_slots: dict[str, dict[str, Any]]


async def _resolve_workflow_input_sources(
    db: AsyncSession,
    *,
    run: Any,
    node: dict[str, Any],
    node_states: dict[str, Any],
) -> _WorkflowInputSources | None:
    file_ids: list[str] = []
    seen_file_ids: set[str] = set()
    input_bindings: dict[str, str] = {}
    standard_input_uploads: dict[str, str] = {}
    binding_decisions: dict[str, dict[str, Any]] = {}
    legacy_file_bindings: dict[str, str] = {}
    semantic_file_bindings: dict[str, str] = {}

    for semantic_type, source in (node.get("semantic_inputs") or {}).items():
        file_id = _workflow_semantic_source_file_id(
            run=run,
            node_states=node_states,
            semantic_type=str(semantic_type),
            source=source,
        )
        if file_id is None:
            return None
        semantic_key = normalize_semantic_type(str(semantic_type))
        await _append_existing_file_id(
            db,
            file_ids=file_ids,
            seen_file_ids=seen_file_ids,
            file_id=file_id,
            label=semantic_key,
        )
        semantic_file_bindings[semantic_key] = file_id

    artifact_slots = artifact_input_slots_by_name_for_node(node)
    for slot_name, source in (node.get("artifact_inputs") or {}).items():
        normalized_slot = str(slot_name)
        if not isinstance(source, str):
            raise ValidationException(f"Unsupported workflow artifact input source: {source}")

        if source.startswith("workflow_input:"):
            artifact_key = source.split(":", 1)[1] or normalized_slot
            file_id = (getattr(run, "input_files", None) or {}).get(artifact_key)
            if not file_id:
                raise ValidationException(
                    f"Workflow run is missing required input: {artifact_key}"
                )
            file_id = str(file_id)
            await _append_existing_file_id(
                db,
                file_ids=file_ids,
                seen_file_ids=seen_file_ids,
                file_id=file_id,
                label=normalized_slot,
            )
            standard_input_uploads[normalized_slot] = file_id
            legacy_file_bindings[normalized_slot] = file_id
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
            source_artifacts = source_state.get("standard_artifacts") or {}
            version_id = _standard_artifact_version_id(source_artifacts, source_output_name)
            slot = artifact_slots.get(normalized_slot)
            if version_id:
                input_bindings[normalized_slot] = str(version_id)
            if slot and _slot_needs_binding_resolution(slot):
                if not version_id:
                    binding_decisions[normalized_slot] = asdict(
                        ArtifactBindingDecision(
                            status="invalid",
                            input_name=normalized_slot,
                            standard_type=str(slot.get("type") or ""),
                            reason=(
                                "Standard artifact version is missing for "
                                f"{source_output_name}."
                            ),
                        )
                    )
                continue

            artifact_file_ids = standard_artifact_file_ids(
                source_artifacts,
                source_output_name,
            )
            if not artifact_file_ids:
                return None
            legacy_file_bindings[normalized_slot] = artifact_file_ids[0]
            for file_id in artifact_file_ids:
                await _append_existing_file_id(
                    db,
                    file_ids=file_ids,
                    seen_file_ids=seen_file_ids,
                    file_id=file_id,
                    label=normalized_slot,
                )
            continue

        raise ValidationException(f"Unsupported workflow artifact input source: {source}")

    return _WorkflowInputSources(
        file_ids=file_ids,
        input_bindings=input_bindings,
        standard_input_uploads=standard_input_uploads,
        binding_decisions=binding_decisions,
        legacy_file_bindings=legacy_file_bindings,
        semantic_file_bindings=semantic_file_bindings,
        artifact_slots=artifact_slots,
    )


def _input_bindings_requiring_validation(
    input_bindings: dict[str, str],
    artifact_inputs_by_name: dict[str, dict[str, Any]],
    *,
    accepts_standard_bindings: bool,
    surface: RunSurface,
) -> dict[str, str]:
    if surface == "tool_detail":
        return input_bindings

    if accepts_standard_bindings:
        return input_bindings

    return {
        slot_name: version_id
        for slot_name, version_id in input_bindings.items()
        if _slot_needs_binding_resolution(
            artifact_inputs_by_name.get(slot_name) or {}
        )
    }


async def _validate_standard_input_bindings(
    db: AsyncSession,
    *,
    project_id: str | None,
    input_bindings: dict[str, str],
) -> None:
    if not input_bindings:
        return
    if not project_id:
        raise ValidationException("标准 ArtifactVersion 输入绑定必须提供 project_id")

    version_ids = set(input_bindings.values())
    result = await db.execute(
        select(ArtifactVersion.id, Artifact.project_id)
        .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
        .where(
            ArtifactVersion.id.in_(version_ids),
            ArtifactVersion.status == "available",
        )
    )
    projects_by_version = {
        str(version_id): str(owner_project_id)
        for version_id, owner_project_id in result.all()
    }
    missing = sorted(version_ids - set(projects_by_version))
    if missing:
        raise ValidationException(
            "输入绑定引用的 ArtifactVersion 不存在",
            detail={"missing_artifact_version_ids": missing},
        )
    mismatched = sorted(
        version_id
        for version_id, owner_project_id in projects_by_version.items()
        if owner_project_id != project_id
    )
    if mismatched:
        raise ValidationException(
            "输入绑定的 ArtifactVersion 必须属于任务关联项目",
            detail={"mismatched_artifact_version_ids": mismatched},
        )


def _slot_needs_binding_resolution(slot: dict[str, Any]) -> bool:
    return any(
        key in slot and slot.get(key) not in (None, "", [])
        for key in (
            "role_preferences",
            "required_roles",
            "readiness_policy",
            "suggested_preparation_tool",
        )
    )


async def _require_existing_file_id(
    db: AsyncSession,
    *,
    file_id: str,
    project_id: str | None,
) -> None:
    file_record = await db.get(FileModel, file_id)
    if not file_record:
        raise ValidationException(
            "标准 Artifact 上传文件不存在",
            detail={"missing_file_id": file_id},
        )
    if project_id and file_record.project_id and str(file_record.project_id) != project_id:
        raise ValidationException(
            "标准 Artifact 上传文件必须属于任务关联项目",
            detail={"mismatched_file_ids": [file_id]},
        )


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


def _workflow_semantic_source_file_id(
    *,
    run: Any,
    node_states: dict[str, Any],
    semantic_type: str,
    source: Any,
) -> str | None:
    if not isinstance(source, str):
        raise ValidationException(f"Unsupported workflow input source: {source}")
    if source.startswith("workflow_input:"):
        semantic_key = normalize_semantic_type(source.split(":", 1)[1] or semantic_type)
        file_id = (getattr(run, "input_files", None) or {}).get(semantic_key)
        if not file_id:
            raise ValidationException(f"Workflow run is missing required input: {semantic_key}")
        return str(file_id)
    if source.startswith("node:"):
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
        file_id = source_output.get("file_id") if isinstance(source_output, dict) else None
        if not file_id:
            raise ValidationException(
                "Workflow node output is not file-backed: "
                f"node={source_node_id}, semantic_type={source_semantic_type}"
            )
        return str(file_id)
    raise ValidationException(f"Unsupported workflow input source: {source}")


def _standard_artifact_version_id(summary: dict[str, Any], output_name: str) -> str | None:
    version_ids_by_ref = summary.get("artifact_version_ids_by_ref")
    if not isinstance(version_ids_by_ref, dict):
        return None
    raw_version_id = version_ids_by_ref.get(output_name)
    if isinstance(raw_version_id, str) and raw_version_id:
        return raw_version_id
    if isinstance(raw_version_id, list):
        for item in raw_version_id:
            if item:
                return str(item)
    indexed_ref = next(
        (
            ref
            for ref in sorted(version_ids_by_ref)
            if isinstance(ref, str) and ref.startswith(f"{output_name}[")
        ),
        None,
    )
    if indexed_ref:
        indexed_version_id = version_ids_by_ref.get(indexed_ref)
        if isinstance(indexed_version_id, str) and indexed_version_id:
            return indexed_version_id
        if isinstance(indexed_version_id, list):
            for item in indexed_version_id:
                if item:
                    return str(item)
    return None


def _first_blocking_binding_reason(decisions: dict[str, dict[str, Any]]) -> str | None:
    for decision in decisions.values():
        if not isinstance(decision, dict) or decision.get("status") == "ready":
            continue
        return str(decision.get("reason") or decision.get("status") or "Artifact binding blocked")
    return None


def _dedupe_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered
