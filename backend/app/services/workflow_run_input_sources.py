"""Resolve workflow node input sources into prepared run inputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.artifact_standards.registry import is_standard_artifact_ref
from app.common.exceptions import ValidationException
from app.common.time import utcnow
from app.files.file_records import is_file_usable
from app.models.artifacts import ArtifactVersion
from app.services.artifact_binding_resolver import ArtifactBindingDecision
from app.services.run_input_validation import (
    append_existing_file_id,
    slot_needs_binding_resolution,
)
from app.services.semantic_types import normalize_semantic_type
from app.services.standard_input_slots import (
    artifact_input_slots_by_name_for_node,
)
from app.services.workflow_artifacts import standard_artifact_file_ids
from app.services.workflow_inputs import (
    WORKFLOW_ARTIFACT_VERSION_PREFIX,
    artifact_matches_workflow_input_type,
    load_project_artifact_version,
)


@dataclass(frozen=True)
class WorkflowInputSources:
    file_ids: list[str]
    input_bindings: dict[str, str]
    standard_input_uploads: dict[str, str]
    binding_decisions: dict[str, dict[str, Any]]
    legacy_file_bindings: dict[str, str]
    semantic_file_bindings: dict[str, str]
    artifact_slots: dict[str, dict[str, Any]]


async def resolve_workflow_input_sources(
    db: AsyncSession,
    *,
    run: Any,
    node: dict[str, Any],
    node_states: dict[str, Any],
) -> WorkflowInputSources | None:
    file_ids: list[str] = []
    seen_file_ids: set[str] = set()
    input_bindings: dict[str, str] = {}
    standard_input_uploads: dict[str, str] = {}
    binding_decisions: dict[str, dict[str, Any]] = {}
    legacy_file_bindings: dict[str, str] = {}
    semantic_file_bindings: dict[str, str] = {}

    for semantic_type, source in (node.get("semantic_inputs") or {}).items():
        file_id = await workflow_semantic_source_file_id(
            db,
            run=run,
            node_states=node_states,
            semantic_type=str(semantic_type),
            source=source,
        )
        if file_id is None:
            return None
        semantic_key = normalize_semantic_type(str(semantic_type))
        await append_existing_file_id(
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
            raise ValidationException(
                f"Unsupported workflow artifact input source: {source}"
            )

        if source.startswith("workflow_input:"):
            artifact_key = source.split(":", 1)[1] or normalized_slot
            if "@" not in artifact_key:
                artifact_key = normalize_semantic_type(artifact_key)
            input_files = getattr(run, "input_files", None) or {}
            input_value = input_files.get(artifact_key)
            if not input_value:
                raise ValidationException(
                    f"Workflow run is missing required input: {artifact_key}"
                )
            if str(input_value).startswith(WORKFLOW_ARTIFACT_VERSION_PREFIX):
                version = await load_workflow_input_version(
                    db,
                    run=run,
                    semantic_type=artifact_key,
                    selection=str(input_value),
                )
                slot = artifact_slots.get(normalized_slot) or {}
                slot_type = str(slot.get("type") or "")
                if is_standard_artifact_ref(slot_type) or slot_needs_binding_resolution(slot):
                    input_bindings[normalized_slot] = str(version.id)
                    continue
                file_id = primary_workflow_artifact_file_id(version, label=normalized_slot)
            else:
                file_id = str(input_value)
            await append_existing_file_id(
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
            resolved = await _resolve_node_artifact_source(
                db,
                source=source,
                normalized_slot=normalized_slot,
                artifact_slots=artifact_slots,
                node_states=node_states,
                file_ids=file_ids,
                seen_file_ids=seen_file_ids,
            )
            if resolved is None:
                return None
            input_bindings.update(resolved.input_bindings)
            binding_decisions.update(resolved.binding_decisions)
            legacy_file_bindings.update(resolved.legacy_file_bindings)
            continue

        raise ValidationException(
            f"Unsupported workflow artifact input source: {source}"
        )

    return WorkflowInputSources(
        file_ids=file_ids,
        input_bindings=input_bindings,
        standard_input_uploads=standard_input_uploads,
        binding_decisions=binding_decisions,
        legacy_file_bindings=legacy_file_bindings,
        semantic_file_bindings=semantic_file_bindings,
        artifact_slots=artifact_slots,
    )


@dataclass(frozen=True)
class _ResolvedNodeArtifactSource:
    input_bindings: dict[str, str]
    binding_decisions: dict[str, dict[str, Any]]
    legacy_file_bindings: dict[str, str]


async def _resolve_node_artifact_source(
    db: AsyncSession,
    *,
    source: str,
    normalized_slot: str,
    artifact_slots: dict[str, dict[str, Any]],
    node_states: dict[str, Any],
    file_ids: list[str],
    seen_file_ids: set[str],
) -> _ResolvedNodeArtifactSource | None:
    parts = source.split(":", 2)
    if len(parts) != 3:
        raise ValidationException(
            f"Invalid workflow artifact input source: {source}"
        )
    source_node_id = parts[1]
    source_output_name = parts[2]
    source_state = node_states.get(source_node_id) or {}
    if source_state.get("status") != "success":
        return None

    source_artifacts = source_state.get("standard_artifacts") or {}
    version_id = standard_artifact_version_id(
        source_artifacts,
        source_output_name,
    )
    slot = artifact_slots.get(normalized_slot)
    input_bindings = {normalized_slot: str(version_id)} if version_id else {}
    binding_decisions: dict[str, dict[str, Any]] = {}
    legacy_file_bindings: dict[str, str] = {}

    if slot and slot_needs_binding_resolution(slot):
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
        return _ResolvedNodeArtifactSource(
            input_bindings=input_bindings,
            binding_decisions=binding_decisions,
            legacy_file_bindings=legacy_file_bindings,
        )

    artifact_file_ids = standard_artifact_file_ids(
        source_artifacts,
        source_output_name,
    )
    if not artifact_file_ids:
        return None
    legacy_file_bindings[normalized_slot] = artifact_file_ids[0]
    for file_id in artifact_file_ids:
        await append_existing_file_id(
            db,
            file_ids=file_ids,
            seen_file_ids=seen_file_ids,
            file_id=file_id,
            label=normalized_slot,
        )
    return _ResolvedNodeArtifactSource(
        input_bindings=input_bindings,
        binding_decisions=binding_decisions,
        legacy_file_bindings=legacy_file_bindings,
    )


async def workflow_semantic_source_file_id(
    db: AsyncSession,
    *,
    run: Any,
    node_states: dict[str, Any],
    semantic_type: str,
    source: Any,
) -> str | None:
    if not isinstance(source, str):
        raise ValidationException(
            f"Unsupported workflow input source: {source}"
        )
    if source.startswith("workflow_input:"):
        semantic_key = normalize_semantic_type(
            source.split(":", 1)[1] or semantic_type
        )
        input_value = (getattr(run, "input_files", None) or {}).get(semantic_key)
        if not input_value:
            raise ValidationException(
                f"Workflow run is missing required input: {semantic_key}"
            )
        if str(input_value).startswith(WORKFLOW_ARTIFACT_VERSION_PREFIX):
            version = await load_workflow_input_version(
                db,
                run=run,
                semantic_type=semantic_key,
                selection=str(input_value),
            )
            return primary_workflow_artifact_file_id(version, label=semantic_key)
        return str(input_value)
    if source.startswith("node:"):
        parts = source.split(":", 2)
        if len(parts) != 3:
            raise ValidationException(
                f"Invalid workflow node input source: {source}"
            )
        source_node_id = parts[1]
        source_semantic_type = normalize_semantic_type(parts[2])
        source_state = node_states.get(source_node_id) or {}
        if source_state.get("status") != "success":
            return None
        source_output = (source_state.get("semantic_outputs") or {}).get(
            source_semantic_type
        )
        if not source_output:
            return None
        file_id = (
            source_output.get("file_id")
            if isinstance(source_output, dict)
            else None
        )
        if not file_id:
            raise ValidationException(
                "Workflow node output is not file-backed: "
                f"node={source_node_id}, semantic_type={source_semantic_type}"
            )
        return str(file_id)
    raise ValidationException(f"Unsupported workflow input source: {source}")


async def load_workflow_input_version(
    db: AsyncSession,
    *,
    run: Any,
    semantic_type: str,
    selection: str,
) -> ArtifactVersion:
    version_id = selection[len(WORKFLOW_ARTIFACT_VERSION_PREFIX):]
    version = await load_project_artifact_version(
        db,
        version_id=version_id,
        project_id=getattr(run, "project_id", None),
    )
    if version.status != "available":
        raise ValidationException(f"Workflow input ArtifactVersion is not available: {semantic_type}")
    if version.expires_at is not None and version.expires_at <= utcnow():
        raise ValidationException(f"Workflow input ArtifactVersion has expired: {semantic_type}")
    if not artifact_matches_workflow_input_type(version, semantic_type):
        raise ValidationException(f"Workflow input ArtifactVersion type does not match: {semantic_type}")
    return version


def primary_workflow_artifact_file_id(version: ArtifactVersion, *, label: str) -> str:
    links = sorted(version.files, key=lambda item: (not item.is_primary, item.sort_order))
    for link in links:
        if link.file is not None and is_file_usable(link.file):
            return str(link.file_id)
    raise ValidationException(f"Workflow input ArtifactVersion has no usable files: {label}")


def standard_artifact_version_id(
    summary: dict[str, Any],
    output_name: str,
) -> str | None:
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
