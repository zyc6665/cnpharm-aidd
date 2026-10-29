"""Transactional typed Artifact creation, versioning, and lineage services."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.time import utcnow
from app.artifact_standards.registry import (
    get_standard_artifact_spec,
    validate_standard_artifact_roles,
)
from app.files.file_records import delete_stored_content
from app.files.writer import store_file_bytes
from app.models.artifacts import (
    Artifact,
    ArtifactLineage,
    ArtifactVersion,
    ArtifactVersionFile,
)
from app.models.files import File as FileModel, FileSourceType
from app.models.projects import Project
from app.models.users import User
from app.services.artifact_writer import upsert_version


def resolve_standard_file_role(
    standard_type: str | None,
    standard_version: int | None,
) -> str:
    """返回上传文件在标准 Artifact 中的角色；未知标准/版本抛 ``StandardArtifactRegistryError``。

    上传入口只有一份文件，角色固定取 registry 里标记 ``primary`` 的那个（没有就取第一
    个）；再交给 :func:`validate_standard_artifact_roles` 过一遍，保证写进
    ``artifact_version_files.role`` 的值一定在受控词表里，避免绕过 registry 直接落库。
    """
    if not (standard_type and standard_version):
        return "input"
    ref = f"{standard_type}@{standard_version}"
    spec = get_standard_artifact_spec(ref)
    primary_role = next((item.role for item in spec.file_roles if item.primary), None)
    role = primary_role or spec.file_roles[0].role
    return validate_standard_artifact_roles(ref, [role])[0]


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
            file_record = None
            try:
                file_record = await _store_uploaded_file(
                    db,
                    project=project,
                    user=user,
                    filename=filename,
                    content=content,
                    content_type=content_type,
                    expires_at=version.expires_at,
                )
                await _link_version_file(
                    db,
                    version=version,
                    file_record=file_record,
                    standard_type=artifact.standard_type,
                    standard_version=artifact.standard_version,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                if file_record is not None:
                    await delete_stored_content(file_record)
                raise
        return artifact

    artifact = Artifact(
        project_id=project.id,
        created_by=user.id,
        artifact_type=artifact_type,
        semantic_type=semantic_type,
        standard_type=standard_type,
        standard_version=standard_version,
        name=Path(filename).name or "artifact.bin",
        description=description,
    )
    db.add(artifact)
    await db.flush()
    file_record = None
    try:
        file_record = await _store_uploaded_file(
            db,
            project=project,
            user=user,
            filename=filename,
            content=content,
            content_type=content_type,
            expires_at=expires_at,
        )
        version, created = await upsert_version(
            db,
            artifact=artifact,
            filename=artifact.name,
            content_type=content_type,
            size_bytes=len(content),
            sha256=digest,
            storage_key=file_record.storage_path,
            storage_etag=None,
            validation_status="pending",
            created_by=user.id,
            source=None,
            expires_at=expires_at,
        )
        if created:
            await _link_version_file(
                db,
                version=version,
                file_record=file_record,
                standard_type=standard_type,
                standard_version=standard_version,
            )
        else:
            # Content-dedup hit: the version already points at a stored blob, so the
            # bytes we just wrote are redundant. Drop both the object and its row.
            await delete_stored_content(file_record)
            await db.delete(file_record)
        setattr(artifact, "deduplicated", not created)
        await db.commit()
        return artifact
    except Exception:
        await db.rollback()
        if file_record is not None:
            await delete_stored_content(file_record)
        raise


async def create_artifact_version(
    db: AsyncSession,
    *,
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
                file_record = None
                try:
                    file_record = await _store_uploaded_file(
                        db,
                        project=project,
                        user=user,
                        filename=filename,
                        content=content,
                        content_type=content_type,
                        expires_at=version.expires_at,
                    )
                    await _link_version_file(
                        db,
                        version=version,
                        file_record=file_record,
                        standard_type=artifact.standard_type,
                        standard_version=artifact.standard_version,
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()
                    if file_record is not None:
                        await delete_stored_content(file_record)
                    raise
            return artifact
    file_record = None
    try:
        file_record = await _store_uploaded_file(
            db,
            project=project,
            user=user,
            filename=filename,
            content=content,
            content_type=content_type,
            expires_at=expires_at,
        )
        version, created = await upsert_version(
            db,
            artifact=artifact,
            filename=Path(filename).name or artifact.name,
            content_type=content_type,
            size_bytes=len(content),
            sha256=digest,
            storage_key=file_record.storage_path,
            storage_etag=None,
            validation_status="pending",
            created_by=user.id,
            source=None,
            expires_at=expires_at,
        )
        if created:
            await _link_version_file(
                db,
                version=version,
                file_record=file_record,
                standard_type=artifact.standard_type,
                standard_version=artifact.standard_version,
            )
        else:
            # Content-dedup hit: drop the redundant object and row.
            await delete_stored_content(file_record)
            await db.delete(file_record)
        setattr(artifact, "deduplicated", not created)
        await db.commit()
        return artifact
    except Exception:
        await db.rollback()
        if file_record is not None:
            await delete_stored_content(file_record)
        raise


async def _store_uploaded_file(
    db: AsyncSession,
    *,
    project: Project,
    user: User,
    filename: str,
    content: bytes,
    content_type: str | None,
    expires_at,
) -> FileModel:
    """写入唯一一份物理内容，返回其 ``File`` 行（路径即版本的 storage_key）。"""
    return await store_file_bytes(
        db,
        content=content,
        filename=filename,
        content_type=content_type,
        source_type=FileSourceType.UPLOAD,
        owner_id=user.id,
        project_id=project.id,
        expires_at=expires_at,
    )


async def _link_version_file(
    db: AsyncSession,
    *,
    version: ArtifactVersion,
    file_record: FileModel,
    standard_type: str | None,
    standard_version: int | None,
) -> None:
    file_record.file_meta = {
        **(file_record.file_meta or {}),
        "artifact_version_id": version.id,
    }
    role = resolve_standard_file_role(standard_type, standard_version)
    db.add(
        ArtifactVersionFile(
            artifact_version_id=version.id,
            role=role,
            file_id=file_record.id,
            is_primary=True,
            sort_order=0,
        )
    )
    # Use db.add rather than version.files.append: when ``version`` was created
    # through the writer it is already flushed, so touching the unloaded
    # ``files`` collection would trigger a lazy load (MissingGreenlet in async).
    await db.flush()


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
