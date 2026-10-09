"""Materialize standard execution artifacts into platform File records."""

from __future__ import annotations

import hashlib
import mimetypes
import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.execution.contracts import ProducedArtifact
from app.files.storage_path import ensure_storage_dir, get_file_path, safe_storage_filename
from app.models.files import File as FileModel, FileSourceType
from app.common.task_context import task_project_id
from app.config import settings
from app.storage.factory import get_storage_backend


class ExecutionArtifactMaterializationError(ValueError):
    """Raised when an execution artifact cannot be safely materialized."""


async def materialize_execution_artifacts(
    db: AsyncSession,
    *,
    task: Any,
    artifacts: list[ProducedArtifact],
    source_root: Path,
) -> list[ProducedArtifact]:
    """Copy adapter output files into platform storage and return file-bound refs."""
    root = Path(source_root).resolve()
    if not root.is_dir():
        raise ExecutionArtifactMaterializationError(
            f"Execution artifact source root does not exist: {source_root}"
        )

    materialized: list[ProducedArtifact] = []
    for artifact in artifacts:
        source_path = _resolve_source_path(root, artifact.path)
        if not source_path.is_file():
            raise ExecutionArtifactMaterializationError(
                f"Execution artifact file does not exist: {artifact.path}"
            )

        content = source_path.read_bytes()
        sha256 = hashlib.sha256(content).hexdigest()
        if artifact.sha256 and sha256 != artifact.sha256.lower():
            raise ExecutionArtifactMaterializationError(
                f"Execution artifact checksum mismatch: {artifact.path}"
            )

        filename = safe_storage_filename(artifact.filename or source_path.name)
        file_id = str(uuid.uuid4())
        storage_backend = settings.STORAGE_BACKEND
        object_key = f"inputs/files/{file_id}/{filename}"
        if storage_backend == "minio":
            stored = await get_storage_backend("minio").upload(
                content,
                object_key,
                artifact.content_type,
            )
            persisted_path = stored.path
        else:
            ensure_storage_dir()
            storage_path = get_file_path(file_id, filename)
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, storage_path)
            persisted_path = str(storage_path)
        file_record = FileModel(
            id=file_id,
            project_id=task_project_id(task),
            owner_id=getattr(task, "user_id", None),
            filename=filename,
            content_type=(
                artifact.content_type
                or mimetypes.guess_type(filename)[0]
                or "application/octet-stream"
            ),
            size_bytes=len(content),
            sha256=sha256,
            storage_backend=storage_backend,
            storage_path=persisted_path,
            source_type=FileSourceType.TOOL_OUTPUT.value,
            is_public=False,
            is_permanent=False,
            file_meta={
                "execution_artifact_path": artifact.path,
                "relative_path": artifact.path,
                "execution_artifact_type": artifact.artifact_type,
                "source_task_id": str(getattr(task, "id", "")),
            },
        )
        db.add(file_record)
        await db.flush()

        materialized.append(
            ProducedArtifact(
                filename=filename,
                path=artifact.path,
                file_id=str(file_record.id),
                content_type=file_record.content_type,
                sha256=sha256,
                artifact_type=artifact.artifact_type,
            )
        )

    return materialized


def _resolve_source_path(root: Path, artifact_path: str) -> Path:
    candidate = Path(str(artifact_path or ""))
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise ExecutionArtifactMaterializationError(
            f"Execution artifact path escapes source root: {artifact_path}"
        )
    return resolved
