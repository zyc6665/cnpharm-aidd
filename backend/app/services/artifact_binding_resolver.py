"""Resolve workflow Artifact bindings against tool input readiness policies."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.artifact_standards.types import normalize_platform_artifact_type
from app.common.time import utcnow
from app.files.file_records import is_file_usable
from app.models.artifacts import ArtifactVersion, ArtifactVersionFile


ArtifactBindingStatus = Literal["ready", "needs_preparation", "needs_conversion", "invalid"]

PROTEIN_STRUCTURE = "protein_structure@1"
LIGAND_STRUCTURE = "ligand_structure@1"
PROTEIN_PREPARATION_TOOL_SLUG = "builtin-protein-preparation"
LIGAND_CONFORMER_TOOL_SLUG = "builtin-rdkit-conformer"


@dataclass(frozen=True)
class ArtifactBindingDecision:
    """Decision returned by the Artifact binding policy resolver."""

    status: ArtifactBindingStatus
    input_name: str
    standard_type: str
    selected_role: str | None = None
    selected_file_id: str | None = None
    artifact_version_id: str | None = None
    reason: str = ""
    suggested_tool_slug: str | None = None


def resolve_artifact_binding_policy(
    *,
    input_slot: Mapping[str, Any],
    artifact_type: str,
    available_roles: Iterable[str] | Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
) -> ArtifactBindingDecision:
    """Select the role that should feed a workflow input, or explain why it cannot."""
    input_name = _input_name(input_slot)
    expected_type = _input_type(input_slot) or normalize_platform_artifact_type(str(artifact_type))
    actual_type = normalize_platform_artifact_type(str(artifact_type))
    role_files = _normalize_role_files(available_roles)
    roles = set(role_files)
    artifact_metadata = metadata or {}

    if expected_type != actual_type:
        return ArtifactBindingDecision(
            status="invalid",
            input_name=input_name,
            standard_type=expected_type,
            reason=f"Expected {expected_type}, received {actual_type}.",
        )

    missing_required_roles = [
        role for role in _list_string_values(input_slot.get("required_roles")) if role not in roles
    ]
    if missing_required_roles:
        return _missing_required_role_decision(
            input_name=input_name,
            standard_type=expected_type,
            missing_roles=missing_required_roles,
        )

    policy = _readiness_policy(input_slot)
    if policy == "require_prepared":
        return _resolve_require_prepared(
            input_name=input_name,
            standard_type=expected_type,
            role_files=role_files,
            metadata=artifact_metadata,
        )
    if policy == "prefer_prepared_warn_raw":
        return _resolve_prefer_prepared_warn_raw(
            input_name=input_name,
            standard_type=expected_type,
            role_files=role_files,
        )
    if policy == "require_receptor":
        return _resolve_require_receptor(
            input_name=input_name,
            standard_type=expected_type,
            role_files=role_files,
        )
    if policy == "prefer_3d_ligand":
        return _resolve_prefer_3d_ligand(
            input_name=input_name,
            standard_type=expected_type,
            role_files=role_files,
            metadata=artifact_metadata,
        )

    return _resolve_allow_raw(
        input_name=input_name,
        standard_type=expected_type,
        role_files=role_files,
        role_preferences=_list_string_values(input_slot.get("role_preferences")),
    )


async def resolve_artifact_binding(
    db: AsyncSession,
    *,
    input_slot: Mapping[str, Any],
    candidate_artifact_version_id: str,
) -> ArtifactBindingDecision:
    """Resolve one tool input against a persisted ArtifactVersion."""
    result = await db.execute(
        select(ArtifactVersion)
        .where(ArtifactVersion.id == candidate_artifact_version_id)
        .options(
            selectinload(ArtifactVersion.artifact),
            selectinload(ArtifactVersion.files).selectinload(ArtifactVersionFile.file),
        )
    )
    version = result.scalar_one_or_none()
    input_name = _input_name(input_slot)
    expected_type = _input_type(input_slot) or ""
    if version is None:
        return ArtifactBindingDecision(
            status="invalid",
            input_name=input_name,
            standard_type=expected_type,
            reason=f"ArtifactVersion {candidate_artifact_version_id} was not found.",
        )
    if version.status != "available":
        return ArtifactBindingDecision(
            status="invalid",
            input_name=input_name,
            standard_type=expected_type,
            artifact_version_id=version.id,
            reason=(
                f"ArtifactVersion {candidate_artifact_version_id} is not available: "
                f"{version.status}."
            ),
        )
    if version.expires_at is not None and version.expires_at <= utcnow():
        return ArtifactBindingDecision(
            status="invalid",
            input_name=input_name,
            standard_type=expected_type,
            artifact_version_id=version.id,
            reason=f"ArtifactVersion {candidate_artifact_version_id} has expired.",
        )

    role_files: dict[str, str | None] = {}
    unavailable_roles: list[str] = []
    for version_file in version.files:
        role = version_file.role
        if not role:
            continue
        if version_file.file is None or not is_file_usable(version_file.file):
            unavailable_roles.append(role)
            continue
        role_files[role] = version_file.file_id

    decision = resolve_artifact_binding_policy(
        input_slot=input_slot,
        artifact_type=_artifact_version_type(version),
        available_roles=role_files,
        metadata=_artifact_version_metadata(version),
    )
    if decision.status != "invalid":
        unavailable_required_roles = _unavailable_required_roles(
            input_slot=input_slot,
            standard_type=decision.standard_type,
            unavailable_roles=unavailable_roles,
        )
        if unavailable_required_roles:
            decision = _invalid(
                input_name=input_name,
                standard_type=decision.standard_type,
                reason=(
                    "Artifact role(s) reference unavailable file(s): "
                    f"{', '.join(unavailable_required_roles)}."
                ),
            )
    return replace(decision, artifact_version_id=version.id)


def _resolve_require_prepared(
    *,
    input_name: str,
    standard_type: str,
    role_files: Mapping[str, str | None],
    metadata: Mapping[str, Any],
) -> ArtifactBindingDecision:
    if standard_type != PROTEIN_STRUCTURE:
        return _invalid(input_name, standard_type, "Prepared protein policy only supports protein_structure@1.")
    if "prepared_pdb" in role_files and metadata.get("preparation_status") == "prepared":
        return _ready(input_name, standard_type, role_files, "prepared_pdb")
    return ArtifactBindingDecision(
        status="needs_preparation",
        input_name=input_name,
        standard_type=standard_type,
        reason="Protein input requires a prepared PDB role.",
        suggested_tool_slug=PROTEIN_PREPARATION_TOOL_SLUG,
    )


def _resolve_prefer_prepared_warn_raw(
    *,
    input_name: str,
    standard_type: str,
    role_files: Mapping[str, str | None],
) -> ArtifactBindingDecision:
    if "prepared_pdb" in role_files:
        return _ready(input_name, standard_type, role_files, "prepared_pdb")
    if "structure_file" in role_files:
        return _ready(
            input_name,
            standard_type,
            role_files,
            "structure_file",
            reason="Raw structure selected; preparation is recommended before downstream modeling.",
            suggested_tool_slug=PROTEIN_PREPARATION_TOOL_SLUG,
        )
    return _invalid(input_name, standard_type, "No usable protein structure role is available.")


def _resolve_require_receptor(
    *,
    input_name: str,
    standard_type: str,
    role_files: Mapping[str, str | None],
) -> ArtifactBindingDecision:
    if standard_type != PROTEIN_STRUCTURE:
        return _invalid(input_name, standard_type, "Receptor policy only supports protein_structure@1.")
    if "receptor_pdbqt" in role_files:
        return _ready(input_name, standard_type, role_files, "receptor_pdbqt")
    return ArtifactBindingDecision(
        status="needs_preparation",
        input_name=input_name,
        standard_type=standard_type,
        reason="Docking input requires receptor_pdbqt.",
        suggested_tool_slug=PROTEIN_PREPARATION_TOOL_SLUG,
    )


def _resolve_prefer_3d_ligand(
    *,
    input_name: str,
    standard_type: str,
    role_files: Mapping[str, str | None],
    metadata: Mapping[str, Any],
) -> ArtifactBindingDecision:
    if standard_type != LIGAND_STRUCTURE:
        return _invalid(input_name, standard_type, "3D ligand policy only supports ligand_structure@1.")
    if "structure_3d_sdf" in role_files:
        return _ready(input_name, standard_type, role_files, "structure_3d_sdf")
    if metadata.get("structure_3d_source") == "2d_only" or "structure_2d_sdf" in role_files:
        return ArtifactBindingDecision(
            status="needs_conversion",
            input_name=input_name,
            standard_type=standard_type,
            reason="Ligand input needs a 3D conformer before this tool can run.",
            suggested_tool_slug=LIGAND_CONFORMER_TOOL_SLUG,
        )
    if "structure_file" in role_files:
        return _ready(input_name, standard_type, role_files, "structure_file")
    return _invalid(input_name, standard_type, "No usable ligand structure role is available.")


def _resolve_allow_raw(
    *,
    input_name: str,
    standard_type: str,
    role_files: Mapping[str, str | None],
    role_preferences: list[str],
) -> ArtifactBindingDecision:
    for role in [*role_preferences, "structure_file", *role_files.keys()]:
        if role in role_files:
            return _ready(input_name, standard_type, role_files, role)
    return _invalid(input_name, standard_type, "No Artifact file roles are available.")


def _missing_required_role_decision(
    *, input_name: str, standard_type: str, missing_roles: list[str]
) -> ArtifactBindingDecision:
    if standard_type == PROTEIN_STRUCTURE and any(
        role in {"prepared_pdb", "receptor_pdbqt"} for role in missing_roles
    ):
        return ArtifactBindingDecision(
            status="needs_preparation",
            input_name=input_name,
            standard_type=standard_type,
            reason=f"Missing required role(s): {', '.join(missing_roles)}.",
            suggested_tool_slug=PROTEIN_PREPARATION_TOOL_SLUG,
        )
    if standard_type == LIGAND_STRUCTURE and "structure_3d_sdf" in missing_roles:
        return ArtifactBindingDecision(
            status="needs_conversion",
            input_name=input_name,
            standard_type=standard_type,
            reason="Missing required role(s): structure_3d_sdf.",
            suggested_tool_slug=LIGAND_CONFORMER_TOOL_SLUG,
        )
    return _invalid(input_name, standard_type, f"Missing required role(s): {', '.join(missing_roles)}.")


def _unavailable_required_roles(
    *,
    input_slot: Mapping[str, Any],
    standard_type: str,
    unavailable_roles: Iterable[str],
) -> list[str]:
    """Return roles that the selected policy cannot use when their files are unavailable."""
    unavailable = set(unavailable_roles)
    required = set(_list_string_values(input_slot.get("required_roles")))
    policy = _readiness_policy(input_slot)
    if policy == "require_prepared" and standard_type == PROTEIN_STRUCTURE:
        required.add("prepared_pdb")
    elif policy == "require_receptor" and standard_type == PROTEIN_STRUCTURE:
        required.add("receptor_pdbqt")
    return sorted(unavailable & required)


def _ready(
    input_name: str,
    standard_type: str,
    role_files: Mapping[str, str | None],
    role: str,
    *,
    reason: str = "",
    suggested_tool_slug: str | None = None,
) -> ArtifactBindingDecision:
    return ArtifactBindingDecision(
        status="ready",
        input_name=input_name,
        standard_type=standard_type,
        selected_role=role,
        selected_file_id=role_files.get(role),
        reason=reason,
        suggested_tool_slug=suggested_tool_slug,
    )


def _invalid(input_name: str, standard_type: str, reason: str) -> ArtifactBindingDecision:
    return ArtifactBindingDecision(status="invalid", input_name=input_name, standard_type=standard_type, reason=reason)


def _input_name(input_slot: Mapping[str, Any]) -> str:
    return str(input_slot.get("name") or input_slot.get("field") or input_slot.get("input_name") or "input")


def _input_type(input_slot: Mapping[str, Any]) -> str | None:
    value = (
        input_slot.get("type")
        or input_slot.get("standard_type")
        or input_slot.get("artifact_type")
        or input_slot.get("semantic_type")
    )
    if value is None:
        return None
    return normalize_platform_artifact_type(str(value))


def _readiness_policy(input_slot: Mapping[str, Any]) -> str:
    policy = input_slot.get("readiness_policy") or input_slot.get("binding_policy") or "allow_raw"
    return str(policy).strip() or "allow_raw"


def _normalize_role_files(available_roles: Iterable[str] | Mapping[str, Any]) -> dict[str, str | None]:
    if isinstance(available_roles, Mapping):
        return {str(role): _file_id(value) for role, value in available_roles.items() if str(role)}
    return {str(role): None for role in available_roles if str(role)}


def _file_id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, Mapping):
        raw_id = value.get("file_id") or value.get("id")
        return str(raw_id) if raw_id else None
    return None


def _list_string_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value if str(item)]
    return []


def _artifact_version_type(version: ArtifactVersion) -> str:
    manifest = version.manifest_json if isinstance(version.manifest_json, Mapping) else {}
    manifest_type = manifest.get("type") or manifest.get("standard_type")
    if manifest_type:
        return normalize_platform_artifact_type(str(manifest_type))

    artifact = version.artifact
    if artifact is not None:
        standard_type = getattr(artifact, "standard_type", None)
        standard_version = getattr(artifact, "standard_version", None)
        if standard_type and standard_version:
            return normalize_platform_artifact_type(f"{standard_type}@{standard_version}")
        artifact_type = getattr(artifact, "artifact_type", None) or getattr(artifact, "semantic_type", None)
        if artifact_type:
            return normalize_platform_artifact_type(str(artifact_type))

    return ""


def _artifact_version_metadata(version: ArtifactVersion) -> Mapping[str, Any]:
    manifest = version.manifest_json if isinstance(version.manifest_json, Mapping) else {}
    metadata = manifest.get("metadata")
    if isinstance(metadata, Mapping):
        return metadata
    return {}
