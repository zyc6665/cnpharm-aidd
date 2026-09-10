"""Materialize direct standard input uploads for Tool Package v2 runs."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.artifact_standards.registry import (
    FileRoleSpec,
    StandardArtifactRegistryError,
    StandardArtifactRef,
    get_standard_artifact_spec,
    parse_standard_ref,
)
from app.common.exceptions import ValidationException
from app.files.storage_path import ensure_storage_dir, get_file_path
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
from app.models.files import File as FileModel
from app.models.files import FileSourceType
from app.models.tools import Tool, ToolVersion
from app.models.users import User
from app.services.tool_contracts import build_tool_contract
from app.tool_packages.config_resolver import tool_package_v2_manifest_data


RoleFile = tuple[str, FileModel, bool]


def accepts_materialized_standard_uploads(config: object) -> bool:
    return tool_package_v2_manifest_data(config) is not None


def standard_uploads_need_default_project(
    standard_input_uploads: dict[str, str] | None,
    config: object,
) -> bool:
    return bool(standard_input_uploads) and accepts_materialized_standard_uploads(config)


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
    uploads = _normalize_upload_mapping(standard_input_uploads)
    if not uploads:
        return {}

    slots_by_name = _artifact_input_slots_by_name(tool, tool_version)
    materialized: dict[str, str] = {}
    for slot_name, file_id in uploads.items():
        slot = _require_slot(slots_by_name, slot_name)
        standard_ref, primary_role, required_roles = _standard_roles_for_slot(slot, slot_name)
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
            if role.role != primary_role.role and not _is_generated_metadata_role(role.role)
        ]
        if unsupported_roles:
            raise ValidationException(
                "标准 Artifact 上传文件无法自动补齐必需文件角色",
                detail={"input_name": slot_name, "missing_roles": unsupported_roles},
            )

        artifact = await _create_input_artifact(
            db,
            current_user=current_user,
            project_id=project_id,
            slot_name=slot_name,
            standard_type=standard_ref.type,
            standard_version=standard_ref.version,
            filename=uploaded_file.filename,
        )
        metadata = _standard_upload_metadata(
            slot_name=slot_name,
            standard_ref=standard_ref.ref,
            uploaded_file=uploaded_file,
        )
        role_files = await _build_role_files(
            db,
            current_user=current_user,
            project_id=project_id,
            slot_name=slot_name,
            primary_role=primary_role.role,
            required_roles=[role.role for role in required_roles],
            uploaded_file=uploaded_file,
            metadata=metadata,
        )
        version = await _create_input_artifact_version(
            db,
            current_user=current_user,
            artifact=artifact,
            standard_ref=standard_ref.ref,
            slot_name=slot_name,
            primary_file=uploaded_file,
            metadata=metadata,
            role_files=role_files,
        )
        await _link_role_files(db, artifact_version_id=version.id, role_files=role_files)
        artifact.latest_version_id = version.id
        artifact.latest_version = version
        materialized[slot_name] = str(version.id)

    await db.flush()
    return materialized


def _normalize_upload_mapping(values: dict[str, str] | None) -> dict[str, str]:
    return {
        str(input_name): str(file_id)
        for input_name, file_id in (values or {}).items()
        if str(input_name).strip() and str(file_id).strip()
    }


def _artifact_input_slots_by_name(tool: Tool, tool_version: ToolVersion) -> dict[str, dict]:
    contract = build_tool_contract(
        SimpleNamespace(
            id=getattr(tool, "id", None),
            slug=getattr(tool, "slug", None),
            name=getattr(tool, "name", None),
            description=getattr(tool, "description", None),
            status=getattr(tool, "status", None),
            is_public=getattr(tool, "is_public", None),
            timeout_sec=getattr(tool, "timeout_sec", None),
            current_version=tool_version,
        )
    )
    artifacts = contract.get("artifacts") if isinstance(contract.get("artifacts"), dict) else {}
    inputs = artifacts.get("inputs") if isinstance(artifacts.get("inputs"), list) else []
    return {
        str(slot.get("name")): slot
        for slot in inputs
        if isinstance(slot, dict) and str(slot.get("name") or "")
    }


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
        raise ValidationException(str(exc), detail={"input_name": slot_name}) from exc
    primary_role = next((role for role in spec.file_roles if role.primary), spec.file_roles[0])
    required_roles = [role for role in spec.file_roles if role.required]
    return standard_ref, primary_role, required_roles


async def _load_standard_upload_file(
    db: AsyncSession,
    *,
    file_id: str,
    project_id: str,
) -> FileModel:
    file_record = await db.get(FileModel, file_id)
    if not file_record:
        raise ValidationException(
            "标准 Artifact 上传文件不存在",
            detail={"missing_file_id": file_id},
        )
    if file_record.project_id and str(file_record.project_id) != project_id:
        raise ValidationException(
            "标准 Artifact 上传文件必须属于任务关联项目",
            detail={"mismatched_file_ids": [file_id]},
        )
    if not file_record.project_id:
        file_record.project_id = project_id
    return file_record


def _validate_primary_upload_format(
    uploaded_file: FileModel,
    *,
    primary_role: FileRoleSpec,
    slot_name: str,
) -> None:
    allowed_formats = {value.lower().lstrip(".") for value in primary_role.allowed_formats}
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


def _is_generated_metadata_role(role: str) -> bool:
    return role.endswith("_json") or "metadata" in role


def _standard_upload_metadata(
    *,
    slot_name: str,
    standard_ref: str,
    uploaded_file: FileModel,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source": "direct_upload",
        "input_name": slot_name,
        "standard_type": standard_ref,
        "source_filename": uploaded_file.filename,
        "source_file_id": str(uploaded_file.id),
        "sha256": uploaded_file.sha256,
    }
    if standard_ref == "molecule_table@1":
        metadata.update(
            _molecule_table_upload_metadata(
                slot_name=slot_name,
                uploaded_file=uploaded_file,
            )
        )
    elif standard_ref == "protein_structure@1":
        metadata.update(_protein_structure_upload_metadata(uploaded_file))
    elif standard_ref == "ligand_structure@1":
        metadata.update(_ligand_structure_upload_metadata(uploaded_file))
    return metadata


def _molecule_table_upload_metadata(
    *,
    slot_name: str,
    uploaded_file: FileModel,
) -> dict[str, object]:
    columns, row_count = _read_molecule_table_shape(uploaded_file)
    return {
        "source_task_id": str(uploaded_file.id),
        "source_input_ref": f"input:{slot_name}",
        "molecule_id_field": _molecule_id_field(columns),
        "row_count": row_count,
        "column_count": len(columns),
        "columns": columns,
    }


def _read_molecule_table_shape(uploaded_file: FileModel) -> tuple[list[str], int]:
    text = _read_text(uploaded_file.storage_path)
    if not text:
        return [], 0
    if Path(uploaded_file.filename).suffix.lower() == ".json":
        return _read_json_table_shape(text)
    return _read_csv_shape(text)


def _read_csv_shape(text: str) -> tuple[list[str], int]:
    reader = csv.DictReader(text.splitlines())
    columns = list(reader.fieldnames or [])
    return columns, sum(1 for _row in reader)


def _read_json_table_shape(text: str) -> tuple[list[str], int]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return [], 0

    rows = _json_table_rows(payload)
    if rows is None:
        return _json_object_shape(payload)
    return _json_rows_shape(rows)


def _json_table_rows(payload: object) -> list[object] | None:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("rows", "data", "items", "molecules"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return None


def _json_rows_shape(rows: list[object]) -> tuple[list[str], int]:
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row:
            column = str(key)
            if column not in seen:
                columns.append(column)
                seen.add(column)
    return columns, len(rows)


def _json_object_shape(payload: object) -> tuple[list[str], int]:
    if not isinstance(payload, dict):
        return [], 0
    return [str(key) for key in payload], 1


def _molecule_id_field(columns: list[str]) -> str:
    lowered = {column.lower(): column for column in columns}
    for candidate in ("molecule_id", "id", "compound_id"):
        if candidate in lowered:
            return lowered[candidate]
    return columns[0] if columns else "molecule_id"


def _protein_structure_upload_metadata(uploaded_file: FileModel) -> dict[str, object]:
    stats = _read_pdb_stats(uploaded_file.storage_path)
    return {
        **stats,
        "structure_format": _structure_format(uploaded_file.filename),
        "source_database": "manual",
        "preparation_status": "raw",
    }


def _ligand_structure_upload_metadata(uploaded_file: FileModel) -> dict[str, object]:
    return {
        "ligand_id": Path(uploaded_file.filename).stem or str(uploaded_file.id),
        "source_database": "manual",
    }


def _read_pdb_stats(storage_path: str | None) -> dict[str, object]:
    text = _read_text(storage_path)
    chains: set[str] = set()
    residues: set[tuple[str, str]] = set()
    atom_count = 0
    for line in text.splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        atom_count += 1
        chain_id = line[21:22].strip() or "_"
        residue_id = line[22:27].strip()
        chains.add(chain_id)
        residues.add((chain_id, residue_id))
    return {
        "chain_ids": sorted(chains),
        "residue_count": len(residues),
        "atom_count": atom_count,
    }


def _structure_format(filename: str) -> str:
    extension = Path(filename).suffix.lower().lstrip(".")
    return "cif" if extension == "cif" else "pdb"


def _read_text(storage_path: str | None) -> str:
    if not storage_path:
        return ""
    path = Path(str(storage_path))
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


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
    file_record = FileModel(
        project_id=project_id,
        owner_id=str(current_user.id),
        filename=filename,
        content_type="application/json",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_path="pending",
        source_type=FileSourceType.SYSTEM.value,
        is_public=False,
        is_permanent=False,
    )
    db.add(file_record)
    await db.flush()

    ensure_storage_dir()
    path = get_file_path(str(file_record.id), filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    file_record.storage_path = str(path)
    await db.flush()
    return file_record
