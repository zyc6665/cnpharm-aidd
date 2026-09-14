"""Plan and validate direct standard Artifact uploads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.artifact_standards.registry import (
    FileRoleSpec,
    StandardArtifactRef,
    StandardArtifactRegistryError,
    get_standard_artifact_spec,
    parse_standard_ref,
)
from app.common.exceptions import ValidationException
from app.models.files import File as FileModel
from app.services.run_input_normalization import normalize_string_mapping
from app.services.standard_input_slots import (
    artifact_input_slots_by_name_for_tool,
    tool_accepts_materialized_standard_uploads,
)
from app.services.standard_upload_metadata import (
    build_standard_upload_metadata,
)


@dataclass(frozen=True)
class StandardInputUploadPlan:
    slot_name: str
    standard_ref: StandardArtifactRef
    primary_role: FileRoleSpec
    required_roles: list[FileRoleSpec]
    uploaded_file: FileModel
    metadata: dict[str, object]


def accepts_materialized_standard_uploads(config: object) -> bool:
    return tool_accepts_materialized_standard_uploads(config)


def standard_uploads_need_default_project(
    standard_input_uploads: dict[str, str] | None,
    config: object,
) -> bool:
    has_uploads = bool(standard_input_uploads)
    return has_uploads and accepts_materialized_standard_uploads(config)


async def validate_standard_input_uploads(
    db: Any,
    *,
    tool: Any,
    tool_version: Any,
    project_id: str | None,
    standard_input_uploads: dict[str, str] | None,
) -> None:
    await build_standard_input_upload_plans(
        db,
        tool=tool,
        tool_version=tool_version,
        project_id=project_id,
        standard_input_uploads=standard_input_uploads,
    )


async def build_standard_input_upload_plans(
    db: Any,
    *,
    tool: Any,
    tool_version: Any,
    project_id: str | None,
    standard_input_uploads: dict[str, str] | None,
) -> list[StandardInputUploadPlan]:
    uploads = normalize_string_mapping(standard_input_uploads)
    if not uploads:
        return []

    slots_by_name = artifact_input_slots_by_name_for_tool(tool, tool_version)
    plans: list[StandardInputUploadPlan] = []
    for slot_name, file_id in uploads.items():
        plans.append(
            await _build_standard_input_upload_plan(
                db,
                slots_by_name=slots_by_name,
                slot_name=slot_name,
                file_id=file_id,
                project_id=project_id,
            )
        )
    return plans


async def _build_standard_input_upload_plan(
    db: Any,
    *,
    slots_by_name: dict[str, dict],
    slot_name: str,
    file_id: str,
    project_id: str | None,
) -> StandardInputUploadPlan:
    slot = _require_slot(slots_by_name, slot_name)
    standard_ref, primary_role, required_roles = _standard_roles_for_slot(
        slot,
        slot_name,
    )
    uploaded_file = await _load_standard_upload_file(
        db,
        file_id=file_id,
        project_id=project_id,
    )
    _validate_primary_upload_format(
        uploaded_file,
        primary_role=primary_role,
        slot_name=slot_name,
    )
    unsupported_roles = [
        role.role
        for role in required_roles
        if role.role != primary_role.role
        and not _is_generated_metadata_role(role.role)
    ]
    if unsupported_roles:
        raise ValidationException(
            "标准 Artifact 上传文件无法自动补齐必需文件角色",
            detail={
                "input_name": slot_name,
                "missing_roles": unsupported_roles,
            },
        )

    return StandardInputUploadPlan(
        slot_name=slot_name,
        standard_ref=standard_ref,
        primary_role=primary_role,
        required_roles=required_roles,
        uploaded_file=uploaded_file,
        metadata=build_standard_upload_metadata(
            slot_name=slot_name,
            standard_ref=standard_ref.ref,
            uploaded_file=uploaded_file,
        ),
    )


def _require_slot(slots_by_name: dict[str, dict], slot_name: str) -> dict:
    slot = slots_by_name.get(slot_name)
    if slot:
        return slot
    raise ValidationException(
        "标准 Artifact 上传输入未在工具契约中声明",
        detail={"input_name": slot_name},
    )


def _standard_roles_for_slot(
    slot: dict,
    slot_name: str,
) -> tuple[StandardArtifactRef, FileRoleSpec, list[FileRoleSpec]]:
    standard_type = str(slot.get("type") or "")
    try:
        standard_ref = parse_standard_ref(standard_type)
        spec = get_standard_artifact_spec(standard_ref.ref)
    except StandardArtifactRegistryError as exc:
        raise ValidationException(
            str(exc),
            detail={"input_name": slot_name},
        ) from exc
    primary_role = next(
        (role for role in spec.file_roles if role.primary),
        spec.file_roles[0],
    )
    required_roles = [role for role in spec.file_roles if role.required]
    return standard_ref, primary_role, required_roles


async def _load_standard_upload_file(
    db: Any,
    *,
    file_id: str,
    project_id: str | None,
) -> FileModel:
    file_record = await db.get(FileModel, file_id)
    if not file_record:
        raise ValidationException(
            "标准 Artifact 上传文件不存在",
            detail={"missing_file_id": file_id},
        )
    if (
        project_id
        and file_record.project_id
        and str(file_record.project_id) != project_id
    ):
        raise ValidationException(
            "标准 Artifact 上传文件必须属于任务关联项目",
            detail={"mismatched_file_ids": [file_id]},
        )
    return file_record


def _validate_primary_upload_format(
    uploaded_file: FileModel,
    *,
    primary_role: FileRoleSpec,
    slot_name: str,
) -> None:
    allowed_formats = {
        value.lower().lstrip(".")
        for value in primary_role.allowed_formats
    }
    if not allowed_formats:
        return

    extension = Path(uploaded_file.filename).suffix.lower().lstrip(".")
    if extension in allowed_formats:
        return
    raise ValidationException(
        "标准 Artifact 上传文件格式不匹配",
        detail={
            "input_name": slot_name,
            "filename": uploaded_file.filename,
            "allowed_formats": sorted(allowed_formats),
        },
    )


def _is_generated_metadata_role(role: str) -> bool:
    return role.endswith("_json") or "metadata" in role
