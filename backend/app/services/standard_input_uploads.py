"""Materialize direct standard input uploads for Tool Package v2 runs."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.files.writer import store_file_bytes
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
from app.models.files import File as FileModel
from app.models.tools import Tool, ToolVersion
from app.models.users import User
from app.services.standard_input_upload_plans import (
    StandardInputUploadPlan,
    accepts_materialized_standard_uploads,
    build_standard_input_upload_plans,
    standard_uploads_need_default_project,
    validate_standard_input_uploads,
)


RoleFile = tuple[str, FileModel, bool]

__all__ = [
    "StandardInputUploadPlan",
    "accepts_materialized_standard_uploads",
    "materialize_standard_input_uploads",
    "standard_uploads_need_default_project",
    "validate_standard_input_uploads",
]


async def materialize_standard_input_uploads(
    db: AsyncSession,
    *,
    current_user: User,
    tool: Tool,
    tool_version: ToolVersion,
    project_id: str,
    standard_input_uploads: dict[str, str] | None,
) -> dict[str, str]:
    """Create ArtifactVersions for direct uploads so v2 runners can consume request.v1."""
    plans = await build_standard_input_upload_plans(
        db,
        tool=tool,
        tool_version=tool_version,
        project_id=project_id,
        standard_input_uploads=standard_input_uploads,
    )
    if not plans:
        return {}

    materialized: dict[str, str] = {}
    for plan in plans:
        if not plan.uploaded_file.project_id:
            plan.uploaded_file.project_id = project_id
        artifact = await _create_input_artifact(
            db,
            current_user=current_user,
            project_id=project_id,
            slot_name=plan.slot_name,
            standard_type=plan.standard_ref.type,
            standard_version=plan.standard_ref.version,
            filename=plan.uploaded_file.filename,
        )
        role_files = await _build_role_files(
            db,
            current_user=current_user,
            project_id=project_id,
            slot_name=plan.slot_name,
            primary_role=plan.primary_role.role,
            required_roles=[role.role for role in plan.required_roles],
            uploaded_file=plan.uploaded_file,
            metadata=plan.metadata,
        )
        version = await _create_input_artifact_version(
            db,
            current_user=current_user,
            artifact=artifact,
            standard_ref=plan.standard_ref.ref,
            slot_name=plan.slot_name,
            primary_file=plan.uploaded_file,
            metadata=plan.metadata,
            role_files=role_files,
        )
        await _link_role_files(
            db,
            artifact_version_id=version.id,
            role_files=role_files,
        )
        artifact.latest_version_id = version.id
        artifact.latest_version = version
        materialized[plan.slot_name] = str(version.id)

    await db.flush()
    return materialized


async def _create_input_artifact(
    db: AsyncSession,
    *,
    current_user: User,
    project_id: str,
    slot_name: str,
    standard_type: str,
    standard_version: int,
    filename: str,
) -> Artifact:
    artifact = Artifact(
        project_id=project_id,
        created_by=str(current_user.id),
        artifact_type=standard_type,
        semantic_type=standard_type,
        standard_type=standard_type,
        standard_version=standard_version,
        name=f"{slot_name}: {filename}",
        description="由工具详情页标准 Artifact 直传输入自动创建。",
    )
    db.add(artifact)
    await db.flush()
    return artifact


async def _build_role_files(
    db: AsyncSession,
    *,
    current_user: User,
    project_id: str,
    slot_name: str,
    primary_role: str,
    required_roles: list[str],
    uploaded_file: FileModel,
    metadata: dict[str, object],
) -> list[RoleFile]:
    role_files = [(primary_role, uploaded_file, True)]
    for role in required_roles:
        if role == primary_role:
            continue
        metadata_file = await _create_standard_upload_metadata_file(
            db,
            current_user=current_user,
            project_id=project_id,
            slot_name=slot_name,
            role=role,
            metadata=metadata,
        )
        role_files.append((role, metadata_file, False))
    return role_files


async def _create_input_artifact_version(
    db: AsyncSession,
    *,
    current_user: User,
    artifact: Artifact,
    standard_ref: str,
    slot_name: str,
    primary_file: FileModel,
    metadata: dict[str, object],
    role_files: list[RoleFile],
) -> ArtifactVersion:
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=str(current_user.id),
        version=1,
        filename=primary_file.filename,
        content_type=primary_file.content_type,
        size_bytes=primary_file.size_bytes,
        sha256=primary_file.sha256,
        storage_key=primary_file.storage_path,
        status="available",
        validation_status="pending",
        validation_errors=[],
        manifest_json={
            "type": standard_ref,
            "input_name": slot_name,
            "files": _role_file_manifest(role_files),
            "metadata": metadata,
        },
        summary_json={},
        metrics_json={},
    )
    db.add(version)
    await db.flush()
    return version


def _role_file_manifest(role_files: list[RoleFile]) -> dict[str, dict]:
    return {
        role: {
            "relative_path": file_record.filename,
            "sha256": file_record.sha256,
            "content_type": file_record.content_type,
        }
        for role, file_record, _is_primary in role_files
    }


async def _link_role_files(
    db: AsyncSession,
    *,
    artifact_version_id: str,
    role_files: list[RoleFile],
) -> None:
    for sort_order, (role, file_record, is_primary) in enumerate(role_files):
        db.add(
            ArtifactVersionFile(
                artifact_version_id=artifact_version_id,
                role=role,
                file_id=file_record.id,
                is_primary=is_primary,
                sort_order=sort_order,
            )
        )


async def _create_standard_upload_metadata_file(
    db: AsyncSession,
    *,
    current_user: User,
    project_id: str,
    slot_name: str,
    role: str,
    metadata: dict[str, object],
) -> FileModel:
    content = json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode("utf-8")
    filename = f"{slot_name}.{role}.json"
    return await store_file_bytes(
        db,
        content=content,
        filename=filename,
        content_type="application/json",
        source_type="system",
        project_id=project_id,
        owner_id=str(current_user.id),
    )
