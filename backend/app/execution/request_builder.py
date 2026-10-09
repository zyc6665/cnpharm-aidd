"""Build standard request.v1 envelopes from persisted ArtifactVersions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.artifact_standards.registry import (
    StandardArtifactRegistryError,
    get_standard_artifact_spec,
    parse_standard_ref,
)
from app.common.time import utcnow
from app.execution.standard_contracts import (
    StandardExecutionContext,
    StandardExecutionRequest,
    StandardFileRef,
    StandardInputArtifact,
    StandardTaskContext,
)
from app.files.file_records import is_file_usable
from app.files.content import ensure_local_file
from app.models.artifacts import ArtifactVersion, ArtifactVersionFile
from app.models.files import File as FileModel
from app.models.tasks import Task
from app.tool_packages.schemas import ArtifactInputV2, ToolPackageV2Manifest


class StandardRequestBuilderError(ValueError):
    """Raised when a standard request.v1 envelope cannot be built."""


@dataclass(frozen=True)
class StandardExecutionBuildContext:
    """Runtime values exposed to the adapter without storage or database credentials."""

    variant: str
    accelerator: str
    work_dir: str = "."
    output_dir: str = "output"


_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]+$")


async def build_standard_execution_request(
    db: AsyncSession,
    *,
    task: Task,
    tool_package_manifest: ToolPackageV2Manifest,
    input_bindings: dict[str, str],
    parameters: dict[str, Any],
    work_dir: Path,
    execution_context: StandardExecutionBuildContext,
) -> StandardExecutionRequest:
    """Stage standard ArtifactVersion inputs and return a request.v1 envelope."""
    declared_inputs = {item.name: item for item in tool_package_manifest.artifacts.inputs}
    unexpected_inputs = sorted(set(input_bindings) - set(declared_inputs))
    if unexpected_inputs:
        raise StandardRequestBuilderError(
            "Input binding references unknown manifest inputs: " + ", ".join(unexpected_inputs)
        )

    staged_inputs: dict[str, StandardInputArtifact] = {}
    for declaration in tool_package_manifest.artifacts.inputs:
        version_id = input_bindings.get(declaration.name)
        if not version_id:
            if declaration.required:
                raise StandardRequestBuilderError(f"Missing required input: {declaration.name}")
            continue
        version = await _load_artifact_version(db, str(version_id))
        _validate_input_type(declaration, version)
        staged_inputs[declaration.name] = await _stage_input_artifact(
            declaration=declaration,
            version=version,
            work_dir=Path(work_dir),
        )

    return StandardExecutionRequest(
        request_version="aidd.sciminer/request.v1",
        task=StandardTaskContext(
            id=str(task.id),
            tool_slug=tool_package_manifest.metadata.slug,
            tool_version=tool_package_manifest.metadata.version,
        ),
        inputs=staged_inputs,
        parameters=dict(parameters),
        execution=StandardExecutionContext(
            variant=execution_context.variant,
            accelerator=execution_context.accelerator,
            work_dir=execution_context.work_dir,
            output_dir=execution_context.output_dir,
        ),
    )


async def _load_artifact_version(db: AsyncSession, version_id: str) -> ArtifactVersion:
    result = await db.execute(
        select(ArtifactVersion)
        .options(
            selectinload(ArtifactVersion.artifact),
            selectinload(ArtifactVersion.files).selectinload(ArtifactVersionFile.file),
        )
        .where(ArtifactVersion.id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise StandardRequestBuilderError(f"ArtifactVersion not found: {version_id}")
    return version


def _validate_input_type(declaration: ArtifactInputV2, version: ArtifactVersion) -> None:
    if version.status != "available":
        raise StandardRequestBuilderError(
            f"ArtifactVersion {version.id} is not available: {version.status}"
        )
    if version.expires_at is not None and version.expires_at <= utcnow():
        raise StandardRequestBuilderError(f"ArtifactVersion {version.id} has expired")

    expected_ref = _parse_ref_for_error(declaration.type)
    actual_ref = _artifact_version_ref(version)
    if actual_ref != expected_ref:
        raise StandardRequestBuilderError(
            f"Input {declaration.name} expects {expected_ref}, got {actual_ref}"
        )

    spec = get_standard_artifact_spec(expected_ref)
    unavailable_roles = [
        file_link.role
        for file_link in version.files
        if file_link.file is None or not is_file_usable(file_link.file)
    ]
    if unavailable_roles:
        raise StandardRequestBuilderError(
            f"Input {declaration.name} references unavailable file roles: "
            + ", ".join(sorted(unavailable_roles))
        )

    available_roles = {file_link.role for file_link in version.files}
    missing_roles = [
        role.role for role in spec.file_roles if role.required and role.role not in available_roles
    ]
    if missing_roles:
        raise StandardRequestBuilderError(
            f"Input {declaration.name} missing required file roles: "
            + ", ".join(missing_roles)
        )


async def _stage_input_artifact(
    *,
    declaration: ArtifactInputV2,
    version: ArtifactVersion,
    work_dir: Path,
) -> StandardInputArtifact:
    input_name = _safe_segment(declaration.name, "input name")
    files: dict[str, StandardFileRef] = {}
    for file_link in sorted(version.files, key=lambda item: item.sort_order):
        role = _safe_segment(file_link.role, "file role")
        file_record = file_link.file
        if file_record is None:
            raise StandardRequestBuilderError(
                f"Input {declaration.name} role {file_link.role} has no file record"
            )
        files[file_link.role] = await _stage_file(
            work_dir=work_dir,
            input_name=input_name,
            role=role,
            file_record=file_record,
        )

    return StandardInputArtifact(
        artifact_version_id=str(version.id),
        type=declaration.type,
        files=files,
        metadata=_metadata_for_version(version),
    )


async def _stage_file(
    *,
    work_dir: Path,
    input_name: str,
    role: str,
    file_record: FileModel,
) -> StandardFileRef:
    destination_dir = work_dir / "input" / input_name
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / _staged_filename(role, file_record.filename)
    try:
        await ensure_local_file(file_record, destination_path)
    except FileNotFoundError as exc:
        raise StandardRequestBuilderError(
            f"Input file does not exist for role {role}: {file_record.storage_path}"
        ) from exc
    relative_path = destination_path.relative_to(work_dir).as_posix()

    return StandardFileRef(
        path=relative_path,
        sha256=str(file_record.sha256).lower(),
        content_type=file_record.content_type,
    )


def _artifact_version_ref(version: ArtifactVersion) -> str:
    artifact = version.artifact
    if artifact and artifact.standard_type and artifact.standard_version:
        return _parse_ref_for_error(f"{artifact.standard_type}@{artifact.standard_version}")
    manifest = version.manifest_json if isinstance(version.manifest_json, dict) else {}
    manifest_type = manifest.get("type")
    if manifest_type:
        return _parse_ref_for_error(str(manifest_type))
    raise StandardRequestBuilderError(
        f"ArtifactVersion {version.id} is not a standard ArtifactVersion"
    )


def _parse_ref_for_error(value: str) -> str:
    try:
        return parse_standard_ref(value).ref
    except StandardArtifactRegistryError as exc:
        raise StandardRequestBuilderError(str(exc)) from exc


def _metadata_for_version(version: ArtifactVersion) -> dict[str, Any]:
    manifest = version.manifest_json if isinstance(version.manifest_json, dict) else {}
    metadata = manifest.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _staged_filename(role: str, filename: str) -> str:
    suffix = "".join(Path(filename).suffixes)
    return f"{role}{suffix}" if suffix else role


def _safe_segment(value: str, label: str) -> str:
    if not _SAFE_SEGMENT.fullmatch(value):
        raise StandardRequestBuilderError(f"Unsafe {label}: {value}")
    return value
