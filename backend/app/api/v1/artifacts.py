"""Project-scoped typed Artifact APIs."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.common.exceptions import ValidationException
from app.common.responses import success_response
from app.common.time import utcnow
from app.config import settings
from app.database.session import get_db
from app.models.artifacts import Artifact
from app.models.users import User
from app.schemas.artifacts import ArtifactMetadata
from app.services.artifacts import create_artifact, create_artifact_version, load_artifact
from app.services.project_access import load_project_membership, require_project_role
from app.storage.factory import get_storage_backend


router = APIRouter()


def get_artifact_storage():
    return get_storage_backend()


async def _content(file: UploadFile) -> bytes:
    maximum = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    content = await file.read(maximum + 1)
    if len(content) > maximum:
        raise ValidationException(f"Artifact 大小超过限制 ({settings.MAX_FILE_SIZE_MB}MB)")
    if not content:
        raise ValidationException("Artifact 内容不能为空")
    return content


def _expires_at(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as exc:
        raise ValidationException("expires_at 必须是 ISO-8601 时间") from exc


def _version_data(version) -> dict:
    return {
        "id": version.id,
        "version": version.version,
        "filename": version.filename,
        "content_type": version.content_type,
        "size_bytes": version.size_bytes,
        "sha256": version.sha256,
        "status": version.status,
        "expires_at": version.expires_at,
        "created_at": version.created_at,
    }


def _artifact_data(artifact: Artifact, *, include_versions: bool = False) -> dict:
    data = {
        "id": artifact.id,
        "project_id": artifact.project_id,
        "artifact_type": artifact.artifact_type,
        "semantic_type": artifact.semantic_type,
        "name": artifact.name,
        "description": artifact.description,
        "latest_version": _version_data(artifact.latest_version),
        "deduplicated": bool(getattr(artifact, "deduplicated", False)),
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }
    if include_versions:
        data["versions"] = [_version_data(version) for version in artifact.versions]
    return data


@router.post("/projects/{project_id}/artifacts", response_model=dict)
async def upload_artifact(
    project_id: str,
    artifact_type: str = Form(...),
    semantic_type: str = Form(...),
    description: str | None = Form(default=None),
    expires_at: str | None = Form(default=None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage=Depends(get_artifact_storage),
):
    project, _ = await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles={"owner", "editor", "runner"},
    )
    metadata = ArtifactMetadata(
        artifact_type=artifact_type,
        semantic_type=semantic_type,
        description=description,
        expires_at=_expires_at(expires_at),
    )
    artifact = await create_artifact(
        db,
        storage=storage,
        project=project,
        user=current_user,
        filename=file.filename or "artifact.bin",
        content=await _content(file),
        content_type=file.content_type,
        **metadata.model_dump(),
    )
    return success_response(data=_artifact_data(artifact), message="Artifact 已保存")


@router.get("/projects/{project_id}/artifacts", response_model=dict)
async def list_artifacts(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await load_project_membership(db, project_id=project_id, user_id=current_user.id)
    artifacts = (
        await db.execute(
            select(Artifact)
            .options(selectinload(Artifact.versions), selectinload(Artifact.latest_version))
            .where(Artifact.project_id == project_id)
            .order_by(Artifact.updated_at.desc())
        )
    ).scalars().all()
    now = utcnow()
    visible = [
        item
        for item in artifacts
        if item.latest_version.status == "available"
        and (item.latest_version.expires_at is None or item.latest_version.expires_at > now)
    ]
    return success_response(data={"items": [_artifact_data(item) for item in visible]})


@router.get("/artifacts/{artifact_id}", response_model=dict)
async def get_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    artifact = await load_artifact(db, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact 不存在")
    await load_project_membership(db, project_id=artifact.project_id, user_id=current_user.id)
    return success_response(data=_artifact_data(artifact, include_versions=True))


@router.post("/artifacts/{artifact_id}/versions", response_model=dict)
async def upload_artifact_version(
    artifact_id: str,
    expires_at: str | None = Form(default=None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage=Depends(get_artifact_storage),
):
    artifact = await load_artifact(db, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact 不存在")
    project, _ = await require_project_role(
        db,
        project_id=artifact.project_id,
        user=current_user,
        allowed_roles={"owner", "editor", "runner"},
    )
    artifact = await create_artifact_version(
        db,
        storage=storage,
        artifact=artifact,
        project=project,
        user=current_user,
        filename=file.filename or artifact.name,
        content=await _content(file),
        content_type=file.content_type,
        expires_at=_expires_at(expires_at),
    )
    return success_response(
        data=_artifact_data(artifact, include_versions=True), message="Artifact 新版本已保存"
    )
