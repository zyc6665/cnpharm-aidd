"""Persist external database records as standard platform Artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.artifact_standards.registry import get_standard_artifact_spec, parse_standard_ref
from app.common.time import utcnow
from app.external_databases.providers import ExternalArtifactFile, ExternalArtifactPayload
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
from app.models.files import File as FileModel, FileSourceType
from app.models.projects import Project
from app.models.users import User
from app.services.artifacts import load_artifact
from app.storage.base import StorageBackend


class ExternalDatabaseImportError(ValueError):
    """Raised when a fetched external record cannot be persisted as a standard Artifact."""


@dataclass(frozen=True)
class ExternalDatabaseImportResult:
    artifact: Artifact


async def persist_external_database_payload(
    db: AsyncSession,
    *,
    storage: StorageBackend,
    project: Project,
    user: User,
    source: str,
    identifier: str,
    payload: ExternalArtifactPayload,
) -> ExternalDatabaseImportResult:
    payload = replace(
        payload,
        metadata=_metadata_with_import_defaults(
            payload.metadata,
            source=source,
            identifier=identifier,
        ),
    )
    standard_ref = parse_standard_ref(payload.standard_ref)
    spec = get_standard_artifact_spec(standard_ref.ref)
    files = _files_with_metadata(payload, spec_roles={role.role for role in spec.file_roles})
    missing_roles = [
        role.role for role in spec.file_roles if role.required and role.role not in files
    ]
    if missing_roles:
        raise ExternalDatabaseImportError(
            "External database payload missing required file roles: " + ", ".join(missing_roles)
        )
    primary_role = next((role.role for role in spec.file_roles if role.primary), None)
    primary_file = files.get(primary_role) if primary_role else next(iter(files.values()))
    if primary_file is None:
        raise ExternalDatabaseImportError("External database payload has no files")

    artifact_id = str(uuid4())
    uploaded_paths: list[str] = []
    try:
        artifact = Artifact(
            id=artifact_id,
            project_id=project.id,
            created_by=user.id,
            artifact_type=standard_ref.type,
            semantic_type=standard_ref.ref,
            standard_type=standard_ref.type,
            standard_version=standard_ref.version,
            name=payload.name,
            description=payload.description,
        )
        version = ArtifactVersion(
            artifact_id=artifact.id,
            created_by=user.id,
            version=1,
            filename=primary_file.filename,
            content_type=primary_file.content_type,
            size_bytes=len(primary_file.content),
            sha256=_sha256(primary_file.content),
            storage_key="",
            status="available",
            validation_status="passed",
            validation_errors=[],
            manifest_json=_manifest(payload, files),
            summary_json={
                "source_database": source,
                "source_id": identifier,
            },
            metrics_json={},
        )
        db.add_all([artifact, version])
        await db.flush()

        file_links: list[ArtifactVersionFile] = []
        for sort_order, (role, artifact_file) in enumerate(files.items()):
            storage_key = _external_object_key(
                organization_id=project.organization_id,
                project_id=project.id,
                artifact_id=artifact.id,
                version=version.version,
                role=role,
                filename=artifact_file.filename,
            )
            stored = await storage.upload(
                artifact_file.content,
                storage_key,
                artifact_file.content_type,
            )
            uploaded_paths.append(stored.path)
            digest = _sha256(artifact_file.content)
            file_record = FileModel(
                project_id=project.id,
                owner_id=user.id,
                filename=artifact_file.filename,
                content_type=artifact_file.content_type,
                size_bytes=len(artifact_file.content),
                sha256=digest,
                storage_path=stored.path,
                source_type=FileSourceType.SYSTEM.value,
                is_public=False,
                is_permanent=False,
                file_meta={
                    "standard_artifact_ref": standard_ref.ref,
                    "standard_artifact_role": role,
                    "source_database": source,
                    "source_id": identifier,
                },
            )
            db.add(file_record)
            await db.flush()
            is_primary = role == primary_role
            file_links.append(
                ArtifactVersionFile(
                    artifact_version_id=version.id,
                    role=role,
                    file_id=file_record.id,
                    is_primary=is_primary,
                    sort_order=sort_order,
                )
            )
            if is_primary:
                version.storage_key = stored.path
                version.storage_etag = stored.etag

        db.add_all(file_links)
        artifact.latest_version_id = version.id
        artifact.latest_version = version
        await db.commit()
    except Exception:
        await db.rollback()
        for path in uploaded_paths:
            await storage.delete(path)
        raise

    loaded = await load_artifact(db, artifact.id)
    if loaded is None:
        raise ExternalDatabaseImportError("Imported Artifact could not be reloaded")
    return ExternalDatabaseImportResult(artifact=loaded)


def _files_with_metadata(
    payload: ExternalArtifactPayload,
    *,
    spec_roles: set[str],
) -> dict[str, ExternalArtifactFile]:
    files = {artifact_file.role: artifact_file for artifact_file in payload.files}
    if "metadata_json" in spec_roles and "metadata_json" not in files:
        metadata_bytes = json.dumps(
            payload.metadata,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        files["metadata_json"] = ExternalArtifactFile(
            role="metadata_json",
            filename="metadata.json",
            content=metadata_bytes,
            content_type="application/json",
        )
    return files


def _metadata_with_import_defaults(
    metadata: dict[str, Any],
    *,
    source: str,
    identifier: str,
) -> dict[str, Any]:
    enriched = dict(metadata)
    enriched.setdefault("source_database", source)
    enriched.setdefault("source_id", identifier)
    enriched.setdefault("fetched_at", utcnow().isoformat())
    return enriched


def _manifest(
    payload: ExternalArtifactPayload,
    files: dict[str, ExternalArtifactFile],
) -> dict[str, Any]:
    return {
        "type": payload.standard_ref,
        "name": payload.name,
        "files": {
            role: {
                "filename": artifact_file.filename,
                "sha256": _sha256(artifact_file.content),
                "content_type": artifact_file.content_type,
            }
            for role, artifact_file in files.items()
        },
        "metadata": payload.metadata,
    }


def _external_object_key(
    *,
    organization_id: str,
    project_id: str,
    artifact_id: str,
    version: int,
    role: str,
    filename: str,
) -> str:
    safe_filename = Path(filename).name or "artifact.bin"
    return (
        f"organizations/{organization_id}/projects/{project_id}/artifacts/"
        f"{artifact_id}/{version}/{role}/{safe_filename}"
    )


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
