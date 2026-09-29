"""Project-scoped typed Artifact APIs."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.common.exceptions import ValidationException
from app.common.responses import success_response
from app.common.time import utcnow
from app.config import settings
from app.database.session import get_db
from app.files.file_records import is_file_usable
from app.logging.audit import AuditAction, AuditResult, get_audit_logger
from app.models.artifacts import (
    Artifact,
    ArtifactLineage,
    ArtifactVersion,
    ArtifactVersionFile,
)
from app.models.tasks import Task
from app.models.users import User
from app.schemas.artifacts import ArtifactMetadata
from app.services.artifacts import (
    create_artifact,
    create_artifact_version,
    load_artifact,
)
from app.services.artifact_responses import (
    artifact_data,
    content_disposition,
    matches_delivery_metadata,
)
from app.services.artifact_lineage_graph import artifact_lineage_graph_data
from app.services.project_access import load_project_membership, require_project_role
from app.storage.factory import get_storage_backend


router = APIRouter()


def get_artifact_storage():
    return get_storage_backend()


async def _content(file: UploadFile) -> bytes:
    maximum = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    content = await file.read(maximum + 1)
    if len(content) > maximum:
        raise ValidationException(
            f"Artifact 大小超过限制 ({settings.MAX_FILE_SIZE_MB}MB)"
        )
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


def _audit_artifact_download(
    *,
    current_user: User,
    artifact: Artifact,
    version: ArtifactVersion,
    file_id: str,
    file_name: str,
    file_size: int | None,
    role: str,
    result: AuditResult = AuditResult.SUCCESS,
    reason: str | None = None,
) -> None:
    extra: dict[str, str | None] = {
        "project_id": artifact.project_id,
        "artifact_id": artifact.id,
        "artifact_version_id": version.id,
        "role": role,
    }
    if reason:
        extra["reason"] = reason
    get_audit_logger().log_file_operation(
        user_id=current_user.id,
        action=AuditAction.FILE_DOWNLOAD,
        file_id=file_id,
        file_name=file_name,
        result=result,
        file_size=file_size,
        **extra,
    )


@router.get("/projects/{project_id}/artifact-lineage", response_model=dict)
async def get_project_artifact_lineage(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await load_project_membership(db, project_id=project_id, user_id=current_user.id)
    artifacts = (
        (
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
                .where(Artifact.project_id == project_id)
                .order_by(Artifact.updated_at.desc(), Artifact.id.desc())
            )
        )
        .scalars()
        .all()
    )
    lineages = (
        (
            await db.execute(
                select(ArtifactLineage)
                .where(ArtifactLineage.project_id == project_id)
                .order_by(ArtifactLineage.created_at.asc(), ArtifactLineage.id.asc())
            )
        )
        .scalars()
        .all()
    )
    source_task_ids = sorted(
        {
            str(artifact.source_task_id)
            for artifact in artifacts
            if artifact.source_task_id
        }
    )
    tasks_by_id: dict[str, Task] = {}
    if source_task_ids:
        tasks = (
            (
                await db.execute(
                    select(Task)
                    .options(selectinload(Task.tool), selectinload(Task.inputs))
                    .where(Task.id.in_(source_task_ids))
                )
            )
            .scalars()
            .all()
        )
        tasks_by_id = {str(task.id): task for task in tasks}

    return success_response(
        data=artifact_lineage_graph_data(
            project_id=project_id,
            artifacts=list(artifacts),
            lineages=list(lineages),
            tasks_by_id=tasks_by_id,
        )
    )


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
    return success_response(data=artifact_data(artifact), message="Artifact 已保存")


@router.get("/projects/{project_id}/artifacts", response_model=dict)
async def list_artifacts(
    project_id: str,
    artifact_type: str | None = None,
    semantic_type: str | None = None,
    standard_type: str | None = None,
    source_task_id: str | None = None,
    file_role: str | None = None,
    metadata_model_name: str | None = None,
    metadata_model_version: str | None = None,
    metadata_evidence_level: str | None = None,
    metadata_endpoint_ref: str | None = None,
    metadata_applicability_domain_status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await load_project_membership(db, project_id=project_id, user_id=current_user.id)
    filters = [Artifact.project_id == project_id]
    if artifact_type:
        filters.append(Artifact.artifact_type == artifact_type)
    if semantic_type:
        filters.append(Artifact.semantic_type == semantic_type)
    if standard_type:
        filters.append(Artifact.standard_type == standard_type)
    if source_task_id:
        filters.append(Artifact.source_task_id == source_task_id)
    if file_role:
        filters.append(
            Artifact.latest_version_id.in_(
                select(ArtifactVersionFile.artifact_version_id).where(
                    ArtifactVersionFile.role == file_role
                )
            )
        )
    artifacts = (
        (
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
                .where(*filters)
                .order_by(Artifact.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    now = utcnow()
    visible = [
        item
        for item in artifacts
        if item.latest_version.status == "available"
        and (
            item.latest_version.expires_at is None
            or item.latest_version.expires_at > now
        )
        and matches_delivery_metadata(
            item,
            model_name=metadata_model_name,
            model_version=metadata_model_version,
            evidence_level=metadata_evidence_level,
            endpoint_ref=metadata_endpoint_ref,
            applicability_domain_status=metadata_applicability_domain_status,
        )
    ]
    return success_response(data={"items": [artifact_data(item) for item in visible]})


@router.get("/artifacts/{artifact_id}", response_model=dict)
async def get_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    artifact = await load_artifact(db, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact 不存在")
    await load_project_membership(
        db, project_id=artifact.project_id, user_id=current_user.id
    )
    return success_response(data=artifact_data(artifact, include_versions=True))


@router.get("/artifacts/{artifact_id}/versions/{version_id}/download")
async def download_artifact_version(
    artifact_id: str,
    version_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage=Depends(get_artifact_storage),
):
    artifact = await load_artifact(db, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact 不存在")
    version = next((item for item in artifact.versions if item.id == version_id), None)
    try:
        await load_project_membership(
            db, project_id=artifact.project_id, user_id=current_user.id
        )
    except HTTPException:
        if version is not None:
            _audit_artifact_download(
                current_user=current_user,
                artifact=artifact,
                version=version,
                file_id=version.id,
                file_name=version.filename,
                file_size=version.size_bytes,
                role="primary",
                result=AuditResult.DENIED,
                reason="project_access_denied",
            )
        raise
    if (
        version is None
        or version.status != "available"
        or (version.expires_at is not None and version.expires_at <= utcnow())
    ):
        raise HTTPException(status_code=404, detail="Artifact 版本不存在")

    content = await storage.download(version.storage_key)
    _audit_artifact_download(
        current_user=current_user,
        artifact=artifact,
        version=version,
        file_id=version.id,
        file_name=version.filename,
        file_size=version.size_bytes,
        role="primary",
    )
    return Response(
        content=content,
        media_type=version.content_type or "application/octet-stream",
        headers={"Content-Disposition": content_disposition(version.filename)},
    )


@router.get("/artifacts/{artifact_id}/versions/{version_id}/files/{role}/download")
async def download_artifact_version_file(
    artifact_id: str,
    version_id: str,
    role: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage=Depends(get_artifact_storage),
):
    artifact = await load_artifact(db, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact 不存在")
    version = next((item for item in artifact.versions if item.id == version_id), None)
    file_link = next((item for item in version.files if item.role == role), None) if version else None
    try:
        await load_project_membership(
            db, project_id=artifact.project_id, user_id=current_user.id
        )
    except HTTPException:
        if version is not None:
            denied_file = file_link.file if file_link and file_link.file else None
            _audit_artifact_download(
                current_user=current_user,
                artifact=artifact,
                version=version,
                file_id=denied_file.id if denied_file else version.id,
                file_name=denied_file.filename if denied_file else version.filename,
                file_size=denied_file.size_bytes if denied_file else version.size_bytes,
                role=role,
                result=AuditResult.DENIED,
                reason="project_access_denied",
            )
        raise
    if (
        version is None
        or version.status != "available"
        or (version.expires_at is not None and version.expires_at <= utcnow())
    ):
        raise HTTPException(status_code=404, detail="Artifact 版本不存在")

    if file_link is None or file_link.file is None:
        raise HTTPException(status_code=404, detail="Artifact 角色文件不存在")
    file_record = file_link.file
    if not is_file_usable(file_record):
        raise HTTPException(status_code=404, detail="Artifact 角色文件不存在")
    content = await storage.download(file_record.storage_path)
    _audit_artifact_download(
        current_user=current_user,
        artifact=artifact,
        version=version,
        file_id=file_record.id,
        file_name=file_record.filename,
        file_size=file_record.size_bytes,
        role=file_link.role,
    )
    return Response(
        content=content,
        media_type=file_record.content_type or "application/octet-stream",
        headers={"Content-Disposition": content_disposition(file_record.filename)},
    )


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
        data=artifact_data(artifact, include_versions=True),
        message="Artifact 新版本已保存",
    )
