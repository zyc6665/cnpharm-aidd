"""Build reusable tool-output artifact file list data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.common.time import utcnow
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
from app.models.files import File as FileModel, FileSourceType
from app.models.tasks import Task
from app.schemas.files import ArtifactFileResponse


@dataclass(frozen=True)
class ArtifactFileSource:
    task: Any
    tool: Any


@dataclass(frozen=True)
class ArtifactFileListResult:
    items: list[dict[str, Any]]
    total: int


async def list_user_artifact_files(
    db: AsyncSession,
    *,
    user_id: str,
    page: int,
    page_size: int,
    search: str | None = None,
) -> ArtifactFileListResult:
    """Return reusable tool-output files for a user."""
    task_result = await db.execute(
        select(Task)
        .options(
            joinedload(Task.tool),
            joinedload(Task.outputs),
        )
        .where(Task.user_id == user_id)
        .order_by(Task.created_at.desc(), Task.id.desc())
    )
    artifact_sources = artifact_sources_by_file_id(task_result.scalars().all())
    if not artifact_sources:
        return ArtifactFileListResult(items=[], total=0)

    query = select(FileModel).where(
        FileModel.id.in_(list(artifact_sources.keys())),
        FileModel.owner_id == user_id,
        FileModel.source_type == FileSourceType.TOOL_OUTPUT.value,
        FileModel.deleted_at.is_(None),
        or_(FileModel.expires_at.is_(None), FileModel.expires_at > utcnow()),
    )

    if search:
        query = query.where(FileModel.filename.ilike(f"%{search}%"))

    total = await _count_query_rows(db, query)
    result = await db.execute(
        query.order_by(FileModel.created_at.desc(), FileModel.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    files = list(result.scalars().all())
    metadata_by_file_id = await _standard_artifact_metadata_by_file_id(
        db,
        [str(file_record.id) for file_record in files],
    )

    items = []
    for file_record in files:
        source = artifact_sources.get(str(file_record.id))
        if not source:
            continue
        items.append(
            artifact_file_item_data(
                file_record,
                source,
                metadata_by_file_id.get(str(file_record.id), {}),
            )
        )

    return ArtifactFileListResult(items=items, total=total)


def artifact_sources_by_file_id(
    tasks: list[Any],
) -> dict[str, ArtifactFileSource]:
    """Map output file IDs to the first task/tool pair that produced them."""
    artifact_sources: dict[str, ArtifactFileSource] = {}
    for task in tasks:
        output_file_ids = _task_output_file_ids(task)
        if not output_file_ids or not task.tool:
            continue
        for file_id in output_file_ids:
            artifact_sources.setdefault(
                str(file_id),
                ArtifactFileSource(task=task, tool=task.tool),
            )
    return artifact_sources


def artifact_file_item_data(
    file_record: Any,
    source: ArtifactFileSource,
    standard_metadata: dict[str, str],
) -> dict[str, Any]:
    """Project a reusable artifact file into the API response shape."""
    task = source.task
    tool = source.tool
    return ArtifactFileResponse(
        id=file_record.id,
        filename=file_record.filename,
        content_type=file_record.content_type,
        size_bytes=file_record.size_bytes,
        source_type=file_record.source_type,
        created_at=file_record.created_at,
        updated_at=file_record.updated_at,
        download_url=f"/api/v1/files/{file_record.id}/download",
        task_id=task.id,
        task_name=task.name,
        tool_id=tool.id,
        tool_name=tool.name,
        tool_slug=tool.slug,
        artifact_id=standard_metadata.get("artifact_id"),
        artifact_version_id=standard_metadata.get("artifact_version_id"),
        standard_artifact_role=standard_metadata.get("standard_artifact_role"),
        standard_artifact_output=standard_metadata.get(
            "standard_artifact_output"
        ),
        semantic_type=standard_metadata.get("semantic_type"),
    ).model_dump()


async def _standard_artifact_metadata_by_file_id(
    db: AsyncSession,
    file_ids: list[str],
) -> dict[str, dict[str, str]]:
    if not file_ids:
        return {}

    result = await db.execute(
        select(
            ArtifactVersionFile.file_id,
            ArtifactVersionFile.role,
            ArtifactVersion.id,
            ArtifactVersion.manifest_json,
            Artifact.id,
            Artifact.standard_type,
            Artifact.standard_version,
            Artifact.semantic_type,
        )
        .join(
            ArtifactVersion,
            ArtifactVersion.id == ArtifactVersionFile.artifact_version_id,
        )
        .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
        .where(ArtifactVersionFile.file_id.in_(file_ids))
    )

    metadata: dict[str, dict[str, str]] = {}
    for (
        file_id,
        role,
        artifact_version_id,
        manifest_json,
        artifact_id,
        standard_type,
        standard_version,
        semantic_type,
    ) in result.all():
        manifest = manifest_json if isinstance(manifest_json, dict) else {}
        standard_ref = manifest.get("type")
        if not standard_ref and standard_type and standard_version:
            standard_ref = f"{standard_type}@{standard_version}"
        metadata[str(file_id)] = {
            "artifact_id": str(artifact_id),
            "artifact_version_id": str(artifact_version_id),
            "standard_artifact_role": str(role),
            "standard_artifact_output": str(manifest.get("output_name") or ""),
            "semantic_type": str(standard_ref or semantic_type or ""),
        }
    return metadata


async def _count_query_rows(db: AsyncSession, query) -> int:
    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    return total_result.scalar() or 0


def _task_output_file_ids(task: Any) -> list[Any]:
    outputs = getattr(task, "outputs", None)
    file_ids = getattr(outputs, "file_ids", None) if outputs else None
    return file_ids if isinstance(file_ids, list) else []
