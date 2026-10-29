"""Materialize direct standard input uploads for Tool Package v2 runs."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.files.writer import store_file_bytes
from app.models.files import File as FileModel
from app.models.tools import Tool, ToolVersion
from app.models.users import User
from app.services.artifact_writer import (
    attach_version_files,
    upsert_artifact,
    upsert_version,
)
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
        artifact, _artifact_created = await upsert_artifact(
            db,
            project_id=project_id,
            artifact_type=plan.standard_ref.type,
            semantic_type=plan.standard_ref.type,
            name=f"{plan.slot_name}: {plan.uploaded_file.filename}",
            description="由工具详情页标准 Artifact 直传输入自动创建。",
            standard_type=plan.standard_ref.type,
            standard_version=plan.standard_ref.version,
            created_by=str(current_user.id),
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
        # 走 ArtifactWriter：版本号由它分配（不再写死 version=1），同内容重复物化时
        # 按 sha256 复用既有版本，角色文件写入也是幂等的。
        version, _version_created = await upsert_version(
            db,
            artifact=artifact,
            filename=plan.uploaded_file.filename,
            content_type=plan.uploaded_file.content_type,
            size_bytes=plan.uploaded_file.size_bytes,
            sha256=plan.uploaded_file.sha256,
            storage_key=plan.uploaded_file.storage_path,
            manifest_json={
                "type": plan.standard_ref.ref,
                "input_name": plan.slot_name,
                "files": _role_file_manifest(role_files),
                "metadata": plan.metadata,
            },
            summary_json={},
            metrics_json={},
            validation_status="pending",
            created_by=str(current_user.id),
            source=None,
        )
        await attach_version_files(
            db,
            version=version,
            files=[
                (role, file_record.id, is_primary)
                for role, file_record, is_primary in role_files
            ],
        )
        artifact.latest_version_id = version.id
        artifact.latest_version = version
        materialized[plan.slot_name] = str(version.id)

    await db.flush()
    return materialized


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


def _role_file_manifest(role_files: list[RoleFile]) -> dict[str, dict]:
    return {
        role: {
            "relative_path": file_record.filename,
            "sha256": file_record.sha256,
            "content_type": file_record.content_type,
        }
        for role, file_record, _is_primary in role_files
    }


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
