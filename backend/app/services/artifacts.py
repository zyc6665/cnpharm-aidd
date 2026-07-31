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
from app.models.artifacts import Artifact, ArtifactLineage, ArtifactVersion
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
    sha256: str,
) -> tuple[Artifact, ArtifactVersion] | None:
    result = await db.execute(
        select(Artifact, ArtifactVersion)
        .join(ArtifactVersion, ArtifactVersion.artifact_id == Artifact.id)
        .where(
            Artifact.project_id == project_id,
            Artifact.artifact_type == artifact_type,
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
    description: str | None = None,
    expires_at=None,
) -> Artifact:
    digest = hashlib.sha256(content).hexdigest()
    duplicate = await _existing_project_content(
        db,
        project_id=project.id,
        artifact_type=artifact_type,
        sha256=digest,
    )
    if duplicate is not None:
        artifact, version = duplicate
        artifact.latest_version = version
        setattr(artifact, "deduplicated", True)
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
    try:
        artifact = Artifact(
            id=artifact_id,
            project_id=project.id,
            created_by=user.id,
            artifact_type=artifact_type,
            semantic_type=semantic_type,
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
        setattr(artifact, "deduplicated", False)
        await db.commit()
        return artifact
    except Exception:
        await db.rollback()
        await storage.delete(object_key)
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
        setattr(artifact, "deduplicated", False)
        await db.commit()
        return artifact
    except Exception:
        await db.rollback()
        await storage.delete(object_key)
        raise


async def load_artifact(db: AsyncSession, artifact_id: str) -> Artifact | None:
    return (
        await db.execute(
            select(Artifact)
            .options(selectinload(Artifact.versions), selectinload(Artifact.latest_version))
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
