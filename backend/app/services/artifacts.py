"""Transactional typed Artifact creation, versioning, and lineage services."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.time import utcnow
from app.artifact_standards.registry import get_standard_artifact_spec, parse_standard_ref
from app.files.file_records import delete_stored_file
from app.files.writer import store_file_bytes
from app.models.artifacts import (
    Artifact,
    ArtifactLineage,
    ArtifactVersion,
    ArtifactVersionFile,
)
from app.models.files import FileSourceType
from app.models.projects import Project
from app.models.users import User
from app.storage.base import StorageBackend


def artifact_object_key(
    *,
    organization_id: str,
    project_id: str,
    artifact_id: str,
    version: int,
    filename: str,
) -> str:
    safe_filename = Path(filename).name or "artifact.bin"
    return (
        f"organizations/{organization_id}/projects/{project_id}/artifacts/"
        f"{artifact_id}/{version}/{safe_filename}"
    )


async def _existing_project_content(
    db: AsyncSession,
    *,
    project_id: str,
    artifact_type: str,
    semantic_type: str,
    standard_type: str | None,
    standard_version: int | None,
    sha256: str,
) -> tuple[Artifact, ArtifactVersion] | None:
    result = await db.execute(
        select(Artifact, ArtifactVersion)
        .join(ArtifactVersion, ArtifactVersion.artifact_id == Artifact.id)
        .options(
            selectinload(ArtifactVersion.files).selectinload(ArtifactVersionFile.file),
        )
        .where(
            Artifact.project_id == project_id,
            Artifact.artifact_type == artifact_type,
            Artifact.semantic_type == semantic_type,
            Artifact.standard_type == standard_type,
            Artifact.standard_version == standard_version,
            ArtifactVersion.sha256 == sha256,
            ArtifactVersion.status == "available",
        )
        .order_by(ArtifactVersion.created_at.desc())
    )
    for artifact, version in result.all():
        if version.expires_at is None or version.expires_at > utcnow():
            return artifact, version
    return None


async def create_artifact(
    db: AsyncSession,
    *,
    storage: StorageBackend,
    project: Project,
    user: User,
    filename: str,
    content: bytes,
    content_type: str | None,
    artifact_type: str,
    semantic_type: str,
    standard_type: str | None = None,
    standard_version: int | None = None,
    description: str | None = None,
    expires_at=None,
) -> Artifact:
    digest = hashlib.sha256(content).hexdigest()
    duplicate = await _existing_project_content(
        db,
        project_id=project.id,
        artifact_type=artifact_type,
        semantic_type=semantic_type,
        standard_type=standard_type,
        standard_version=standard_version,
        sha256=digest,
    )
    if duplicate is not None:
        artifact, version = duplicate
        artifact.latest_version = version
        setattr(artifact, "deduplicated", True)
        if not version.files:
            file_record = await _attach_uploaded_file(
                db,
                version=version,
                project=project,
                user=user,
                filename=filename,
                content=content,
                content_type=content_type,
                expires_at=version.expires_at,
                standard_type=artifact.standard_type,
                standard_version=artifact.standard_version,
            )
            local_storage_path = file_record.storage_path
            try:
                await db.commit()
            except Exception:
                await db.rollback()
                Path(local_storage_path).unlink(missing_ok=True)
                raise
        return artifact

    artifact_id = str(uuid4())
    object_key = artifact_object_key(
        organization_id=project.organization_id,
        project_id=project.id,
        artifact_id=artifact_id,
        version=1,
        filename=filename,
    )
    stored = await storage.upload(content, object_key, content_type)
    file_record = None
    local_storage_path = None
    try:
        artifact = Artifact(
            id=artifact_id,
            project_id=project.id,
            created_by=user.id,
            artifact_type=artifact_type,
            semantic_type=semantic_type,
            standard_type=standard_type,
            standard_version=standard_version,
            name=Path(filename).name or "artifact.bin",
            description=description,
        )
        version = ArtifactVersion(
            artifact_id=artifact.id,
            created_by=user.id,
            version=1,
            filename=artifact.name,
            content_type=content_type,
            size_bytes=len(content),
            sha256=digest,
            storage_key=object_key,
            storage_etag=stored.etag,
            status="available",
            expires_at=expires_at,
        )
        db.add_all([artifact, version])
        await db.flush()
        artifact.latest_version_id = version.id
        artifact.latest_version = version
        file_record = await _attach_uploaded_file(
            db,
            version=version,
            project=project,
            user=user,
            filename=filename,
            content=content,
            content_type=content_type,
            expires_at=expires_at,
            standard_type=standard_type,
            standard_version=standard_version,
        )
        local_storage_path = file_record.storage_path
        setattr(artifact, "deduplicated", False)
        await db.commit()
        return artifact
    except Exception:
        await db.rollback()
        await storage.delete(object_key)
        if local_storage_path:
            Path(local_storage_path).unlink(missing_ok=True)
        raise


async def create_artifact_version(
    db: AsyncSession,
    *,
    storage: StorageBackend,
    artifact: Artifact,
    project: Project,
    user: User,
    filename: str,
    content: bytes,
    content_type: str | None,
    expires_at=None,
) -> Artifact:
    digest = hashlib.sha256(content).hexdigest()
    for version in artifact.versions:
        if version.sha256 == digest and version.status == "available":
            artifact.latest_version = version
            setattr(artifact, "deduplicated", True)
            if not version.files:
                file_record = await _attach_uploaded_file(
                    db,
                    version=version,
                    project=project,
                    user=user,
                    filename=filename,
                    content=content,
                    content_type=content_type,
                    expires_at=version.expires_at,
                    standard_type=artifact.standard_type,
                    standard_version=artifact.standard_version,
                )
                local_storage_path = file_record.storage_path
                try:
                    await db.commit()
                except Exception:
                    await db.rollback()
                    Path(local_storage_path).unlink(missing_ok=True)
                    raise
            return artifact
    number = max((version.version for version in artifact.versions), default=0) + 1
    object_key = artifact_object_key(
        organization_id=project.organization_id,
        project_id=project.id,
        artifact_id=artifact.id,
        version=number,
        filename=filename,
    )
    stored = await storage.upload(content, object_key, content_type)
    file_record = None
    local_storage_path = None
    try:
        version = ArtifactVersion(
            artifact_id=artifact.id,
            created_by=user.id,
            version=number,
            filename=Path(filename).name or artifact.name,
            content_type=content_type,
            size_bytes=len(content),
            sha256=digest,
            storage_key=object_key,
            storage_etag=stored.etag,
            status="available",
            expires_at=expires_at,
        )
        db.add(version)
        await db.flush()
        artifact.latest_version_id = version.id
        artifact.latest_version = version
        file_record = await _attach_uploaded_file(
            db,
            version=version,
            project=project,
            user=user,
            filename=filename,
            content=content,
            content_type=content_type,
            expires_at=expires_at,
            standard_type=artifact.standard_type,
            standard_version=artifact.standard_version,
        )
        local_storage_path = file_record.storage_path
        setattr(artifact, "deduplicated", False)
        await db.commit()
        return artifact
    except Exception:
        await db.rollback()
        await storage.delete(object_key)
        if local_storage_path:
            Path(local_storage_path).unlink(missing_ok=True)
        raise


async def _attach_uploaded_file(
    db: AsyncSession,
    *,
    version: ArtifactVersion,
    project: Project,
    user: User,
    filename: str,
    content: bytes,
    content_type: str | None,
    expires_at,
    standard_type: str | None,
    standard_version: int | None,
):
    file_record = await store_file_bytes(
        db,
        content=content,
        filename=filename,
        content_type=content_type,
        source_type=FileSourceType.UPLOAD,
        owner_id=user.id,
        project_id=project.id,
        expires_at=expires_at,
        file_meta={"artifact_version_id": version.id},
    )
    try:
        role = "input"
        if standard_type and standard_version:
            standard_ref = parse_standard_ref(f"{standard_type}@{standard_version}")
            spec = get_standard_artifact_spec(standard_ref.ref)
            primary_role = next((item.role for item in spec.file_roles if item.primary), None)
            role = primary_role or spec.file_roles[0].role
        link = ArtifactVersionFile(
            artifact_version_id=version.id,
            role=role,
            file=file_record,
            is_primary=True,
            sort_order=0,
        )
        version.files.append(link)
        await db.flush()
        return file_record
    except Exception:
        delete_stored_file(file_record)
        raise


async def load_artifact(db: AsyncSession, artifact_id: str) -> Artifact | None:
    return (
        await db.execute(
            select(Artifact)
            .options(
                selectinload(Artifact.versions)
                .selectinload(ArtifactVersion.files)
                .selectinload(ArtifactVersionFile.file),
                selectinload(Artifact.latest_version)
                .selectinload(ArtifactVersion.files)
                .selectinload(ArtifactVersionFile.file),
            )
            .where(Artifact.id == artifact_id)
        )
    ).scalar_one_or_none()


async def link_artifact_lineage(
    db: AsyncSession,
    *,
    project_id: str,
    input_version_id: str,
    output_version_id: str,
    user_id: str,
) -> ArtifactLineage:
    rows = (
        await db.execute(
            select(ArtifactVersion.id, Artifact.project_id)
            .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
            .where(ArtifactVersion.id.in_({input_version_id, output_version_id}))
        )
    ).all()
    projects_by_version = {str(version_id): str(owner_project_id) for version_id, owner_project_id in rows}
    if input_version_id not in projects_by_version or output_version_id not in projects_by_version:
        raise HTTPException(status_code=404, detail="Artifact 版本不存在")
    if any(value != project_id for value in projects_by_version.values()):
        raise HTTPException(status_code=403, detail="禁止跨项目建立 Artifact 谱系")
    existing = (
        await db.execute(
            select(ArtifactLineage).where(
                ArtifactLineage.input_version_id == input_version_id,
                ArtifactLineage.output_version_id == output_version_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    edge = ArtifactLineage(
        project_id=project_id,
        input_version_id=input_version_id,
        output_version_id=output_version_id,
        created_by=user_id,
    )
    db.add(edge)
    await db.commit()
    return edge
