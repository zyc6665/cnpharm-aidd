"""Response projection helpers for typed Artifacts."""

from __future__ import annotations

from urllib.parse import quote
from typing import Any

from sqlalchemy import inspect

from app.files.file_records import is_file_usable
from app.models.artifacts import Artifact, ArtifactVersionFile


def artifact_data(
    artifact: Artifact,
    *,
    include_versions: bool = False,
) -> dict[str, Any]:
    data = {
        "id": artifact.id,
        "project_id": artifact.project_id,
        "artifact_type": artifact.artifact_type,
        "semantic_type": artifact.semantic_type,
        "standard_type": artifact.standard_type,
        "standard_version": artifact.standard_version,
        "name": artifact.name,
        "description": artifact.description,
        "latest_version": version_data(
            artifact.latest_version,
            artifact_id=artifact.id,
        ),
        "deduplicated": bool(getattr(artifact, "deduplicated", False)),
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }
    if include_versions:
        data["versions"] = [
            version_data(version, artifact_id=artifact.id)
            for version in artifact.versions
        ]
    return data


def version_data(
    version: Any,
    *,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": version.id,
        "version": version.version,
        "filename": version.filename,
        "content_type": version.content_type,
        "size_bytes": version.size_bytes,
        "sha256": version.sha256,
        "status": version.status,
        "manifest_json": version.manifest_json,
        "expires_at": version.expires_at,
        "created_at": version.created_at,
        "files": _version_files_data(artifact_id=artifact_id, version=version)
        if artifact_id
        else [],
    }


def matches_delivery_metadata(
    artifact: Artifact,
    *,
    model_name: str | None,
    model_version: str | None,
    evidence_level: str | None,
    endpoint_ref: str | None,
    applicability_domain_status: str | None,
) -> bool:
    artifact_model_name = _artifact_metadata_value(artifact, "model_name")
    if model_name and artifact_model_name != model_name:
        return False

    artifact_model_version = _artifact_metadata_value(
        artifact,
        "model_version",
    )
    if (
        model_version
        and artifact_model_version != model_version
    ):
        return False

    artifact_evidence_level = _artifact_metadata_value(
        artifact,
        "evidence_level",
    )
    if (
        evidence_level
        and artifact_evidence_level != evidence_level
    ):
        return False

    artifact_endpoint_ref = _artifact_metadata_value(artifact, "endpoint_ref")
    if endpoint_ref and artifact_endpoint_ref != endpoint_ref:
        return False

    artifact_domain_status = _artifact_metadata_value(
        artifact,
        "applicability_domain_status",
    )
    if (
        applicability_domain_status
        and artifact_domain_status != applicability_domain_status
    ):
        return False
    return True


def content_disposition(filename: str) -> str:
    safe_filename = filename.replace('"', "")
    return (
        f"attachment; filename=\"{safe_filename}\"; "
        f"filename*=UTF-8''{quote(filename)}"
    )


def _version_file_data(
    *,
    artifact_id: str,
    version_id: str,
    file_link: ArtifactVersionFile,
) -> dict[str, Any]:
    file_record = file_link.file
    return {
        "id": file_link.id,
        "role": file_link.role,
        "file_id": file_link.file_id,
        "is_primary": file_link.is_primary,
        "sort_order": file_link.sort_order,
        "filename": file_record.filename if file_record else None,
        "content_type": file_record.content_type if file_record else None,
        "size_bytes": file_record.size_bytes if file_record else None,
        "sha256": file_record.sha256 if file_record else None,
        "download_url": (
            f"/api/v1/artifacts/{artifact_id}/versions/{version_id}"
            f"/files/{quote(file_link.role, safe='')}/download"
        ),
    }


def _version_files_data(
    *,
    artifact_id: str | None,
    version: Any,
) -> list[dict]:
    if not artifact_id or "files" in inspect(version).unloaded:
        return []
    return [
        _version_file_data(
            artifact_id=artifact_id,
            version_id=version.id,
            file_link=file_link,
        )
        for file_link in version.files
        if file_link.file is not None and is_file_usable(file_link.file)
    ]


def _artifact_metadata_value(artifact: Artifact, key: str) -> str | None:
    manifest = artifact.latest_version.manifest_json
    if not isinstance(manifest, dict):
        return None
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    if value is None:
        return None
    return str(value)
