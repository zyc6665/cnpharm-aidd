"""Project-scoped typed Artifact APIs."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.common.exceptions import ValidationException
from app.common.responses import success_response
from app.common.time import utcnow
from app.config import settings
from app.database.session import get_db
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


def _version_file_data(
    *, artifact_id: str, version_id: str, file_link: ArtifactVersionFile
) -> dict:
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


def _version_files_data(*, artifact_id: str, version) -> list[dict]:
    if "files" in inspect(version).unloaded:
        return []
    return [
        _version_file_data(
            artifact_id=artifact_id,
            version_id=version.id,
            file_link=file_link,
        )
        for file_link in version.files
    ]


def _version_data(version, *, artifact_id: str | None = None) -> dict:
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


def _artifact_data(artifact: Artifact, *, include_versions: bool = False) -> dict:
    data = {
        "id": artifact.id,
        "project_id": artifact.project_id,
        "artifact_type": artifact.artifact_type,
        "semantic_type": artifact.semantic_type,
        "standard_type": artifact.standard_type,
        "standard_version": artifact.standard_version,
        "name": artifact.name,
        "description": artifact.description,
        "latest_version": _version_data(artifact.latest_version, artifact_id=artifact.id),
        "deduplicated": bool(getattr(artifact, "deduplicated", False)),
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }
    if include_versions:
        data["versions"] = [
            _version_data(version, artifact_id=artifact.id) for version in artifact.versions
        ]
    return data


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


def _matches_delivery_metadata(
    artifact: Artifact,
    *,
    model_version: str | None,
    evidence_level: str | None,
) -> bool:
    if model_version and _artifact_metadata_value(artifact, "model_version") != model_version:
        return False
    if evidence_level and _artifact_metadata_value(artifact, "evidence_level") != evidence_level:
        return False
    return True


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


def _add_graph_node(nodes: dict[str, dict], node: dict) -> None:
    nodes[str(node["id"])] = node


def _add_graph_edge(edges: dict[tuple[str, str, str], dict], edge: dict) -> None:
    key = (str(edge["source"]), str(edge["target"]), str(edge["kind"]))
    edges[key] = edge


def _task_workflow_params(task: Task) -> dict:
    params = task.inputs.params if task.inputs else {}
    return params if isinstance(params, dict) else {}


def _artifact_lineage_graph_data(
    *,
    project_id: str,
    artifacts: list[Artifact],
    lineages: list[ArtifactLineage],
    tasks_by_id: dict[str, Task],
) -> dict:
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], dict] = {}
    version_ids: set[str] = set()

    for artifact in artifacts:
        artifact_node_id = f"artifact:{artifact.id}"
        _add_graph_node(
            nodes,
            {
                "id": artifact_node_id,
                "kind": "artifact",
                "artifact_id": artifact.id,
                "project_id": artifact.project_id,
                "label": artifact.name,
                "name": artifact.name,
                "artifact_type": artifact.artifact_type,
                "semantic_type": artifact.semantic_type,
                "standard_type": artifact.standard_type,
                "standard_version": artifact.standard_version,
                "source_task_id": artifact.source_task_id,
                "latest_version_id": artifact.latest_version_id,
                "created_at": artifact.created_at,
                "updated_at": artifact.updated_at,
            },
        )
        for version in artifact.versions:
            version_ids.add(str(version.id))
            version_node_id = f"version:{version.id}"
            _add_graph_node(
                nodes,
                {
                    "id": version_node_id,
                    "kind": "version",
                    "artifact_id": artifact.id,
                    "version_id": version.id,
                    "label": f"{artifact.name} v{version.version}",
                    "version": version.version,
                    "filename": version.filename,
                    "content_type": version.content_type,
                    "size_bytes": version.size_bytes,
                    "sha256": version.sha256,
                    "status": version.status,
                    "validation_status": version.validation_status,
                    "created_at": version.created_at,
                },
            )
            _add_graph_edge(
                edges,
                {
                    "id": f"{artifact_node_id}->{version_node_id}:has_version",
                    "kind": "has_version",
                    "source": artifact_node_id,
                    "target": version_node_id,
                },
            )
            if artifact.source_task_id:
                task_node_id = f"task:{artifact.source_task_id}"
                _add_graph_edge(
                    edges,
                    {
                        "id": f"{task_node_id}->{version_node_id}:produced_by",
                        "kind": "produced_by",
                        "source": task_node_id,
                        "target": version_node_id,
                    },
                )

    for task_id, task in tasks_by_id.items():
        tool = task.tool
        task_node_id = f"task:{task_id}"
        _add_graph_node(
            nodes,
            {
                "id": task_node_id,
                "kind": "task",
                "task_id": task_id,
                "label": task.name or (tool.name if tool else task_id),
                "name": task.name,
                "status": task.status,
                "tool_id": task.tool_id,
                "tool_name": tool.name if tool else None,
                "tool_slug": tool.slug if tool else None,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            },
        )
        params = _task_workflow_params(task)
        run_id = params.get("workflow_run_id")
        node_id = params.get("workflow_node_id")
        if not run_id or not node_id:
            continue
        workflow_node_id = f"workflow-node:{run_id}:{node_id}"
        _add_graph_node(
            nodes,
            {
                "id": workflow_node_id,
                "kind": "workflow_node",
                "workflow_run_id": str(run_id),
                "workflow_definition_id": (
                    str(params["workflow_definition_id"])
                    if params.get("workflow_definition_id")
                    else None
                ),
                "workflow_node_id": str(node_id),
                "workflow_node_type": str(params.get("workflow_node_type") or "tool"),
                "label": str(node_id),
                "task_id": task_id,
            },
        )
        _add_graph_edge(
            edges,
            {
                "id": f"{workflow_node_id}->{task_node_id}:runs_task",
                "kind": "runs_task",
                "source": workflow_node_id,
                "target": task_node_id,
            },
        )

    for lineage in lineages:
        source = f"version:{lineage.input_version_id}"
        target = f"version:{lineage.output_version_id}"
        if lineage.input_version_id not in version_ids or lineage.output_version_id not in version_ids:
            continue
        relation_type = lineage.relation_type or "derived_from"
        _add_graph_edge(
            edges,
            {
                "id": f"{source}->{target}:{relation_type}",
                "kind": relation_type,
                "source": source,
                "target": target,
                "lineage_id": lineage.id,
                "project_id": lineage.project_id,
                "relation_type": relation_type,
                "created_at": lineage.created_at,
            },
        )

    return {
        "project_id": project_id,
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "summary": {
            "artifacts": len(artifacts),
            "versions": len(version_ids),
            "tasks": len(tasks_by_id),
            "workflow_nodes": sum(1 for node in nodes.values() if node["kind"] == "workflow_node"),
            "lineage_edges": len(lineages),
        },
    }


def _content_disposition(filename: str) -> str:
    safe_filename = filename.replace('"', "")
    return (
        f"attachment; filename=\"{safe_filename}\"; filename*=UTF-8''{quote(filename)}"
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
        data=_artifact_lineage_graph_data(
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
    return success_response(data=_artifact_data(artifact), message="Artifact 已保存")


@router.get("/projects/{project_id}/artifacts", response_model=dict)
async def list_artifacts(
    project_id: str,
    artifact_type: str | None = None,
    semantic_type: str | None = None,
    standard_type: str | None = None,
    source_task_id: str | None = None,
    file_role: str | None = None,
    metadata_model_version: str | None = None,
    metadata_evidence_level: str | None = None,
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
        and _matches_delivery_metadata(
            item,
            model_version=metadata_model_version,
            evidence_level=metadata_evidence_level,
        )
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
    await load_project_membership(
        db, project_id=artifact.project_id, user_id=current_user.id
    )
    return success_response(data=_artifact_data(artifact, include_versions=True))


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
        headers={"Content-Disposition": _content_disposition(version.filename)},
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
        headers={"Content-Disposition": _content_disposition(file_record.filename)},
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
        data=_artifact_data(artifact, include_versions=True),
        message="Artifact 新版本已保存",
    )
