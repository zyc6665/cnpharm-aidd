"""Validate prepared run input file and Artifact bindings."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundException, ValidationException
from app.common.time import utcnow
from app.files.file_records import is_file_usable
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.files import File as FileModel


def input_bindings_requiring_validation(
    input_bindings: dict[str, str],
    artifact_inputs_by_name: dict[str, dict[str, Any]],
    *,
    accepts_standard_bindings: bool,
    surface: str,
) -> dict[str, str]:
    if surface == "tool_detail":
        return input_bindings

    if accepts_standard_bindings:
        return input_bindings

    return {
        slot_name: version_id
        for slot_name, version_id in input_bindings.items()
        if slot_needs_binding_resolution(
            artifact_inputs_by_name.get(slot_name) or {}
        )
    }


async def validate_standard_input_bindings(
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
            (ArtifactVersion.expires_at.is_(None)) | (ArtifactVersion.expires_at > utcnow()),
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


def slot_needs_binding_resolution(slot: dict[str, Any]) -> bool:
    return any(
        key in slot and slot.get(key) not in (None, "", [])
        for key in (
            "role_preferences",
            "required_roles",
            "readiness_policy",
            "suggested_preparation_tool",
        )
    )


async def require_existing_file_id(
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
    if not is_file_usable(file_record):
        raise ValidationException(
            "标准 Artifact 上传文件不可用",
            detail={"unusable_file_ids": [file_id]},
        )
    mismatched_project = (
        project_id
        and file_record.project_id
        and str(file_record.project_id) != project_id
    )
    if mismatched_project:
        raise ValidationException(
            "标准 Artifact 上传文件必须属于任务关联项目",
            detail={"mismatched_file_ids": [file_id]},
        )


async def append_existing_file_id(
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
    if not is_file_usable(file_record):
        raise NotFoundException(f"Workflow input file not found: {label}")
    if file_id not in seen_file_ids:
        seen_file_ids.add(file_id)
        file_ids.append(file_id)


def dedupe_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered
