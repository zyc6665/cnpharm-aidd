"""ArtifactVersion writer: single place that allocates version numbers and records
where a version came from, plus the input→output lineage edges for a task.

The public surface is :class:`ArtifactSource` and :func:`upsert_version`.  Callers
keep their existing ``create_artifact`` / ``create_artifact_version`` /
``_persist_artifact`` signatures; only their internals delegate here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.models.artifacts import (
    Artifact,
    ArtifactLineage,
    ArtifactVersion,
    ArtifactVersionFile,
)
from app.models.traceability import TaskInputSnapshot


MAX_VERSION_RETRIES = 3


@dataclass(frozen=True)
class ArtifactSource:
    """Where a freshly produced ArtifactVersion came from (task / attempt / tool version)."""

    task_id: str | None = None
    attempt_id: str | None = None
    tool_version_id: str | None = None


def _dialect_name(db: AsyncSession) -> str:
    bind = db.get_bind()
    if bind is None:
        return ""
    return getattr(bind.dialect, "name", "") or ""


async def _max_version_number(db: AsyncSession, artifact_id: str) -> int:
    current = await db.scalar(
        select(func.max(ArtifactVersion.version)).where(
            ArtifactVersion.artifact_id == artifact_id
        )
    )
    return int(current or 0)


async def _find_available_version_by_sha(
    db: AsyncSession, *, artifact_id: str, sha256: str
) -> ArtifactVersion | None:
    result = await db.execute(
        select(ArtifactVersion)
        .where(
            ArtifactVersion.artifact_id == artifact_id,
            ArtifactVersion.sha256 == sha256,
            ArtifactVersion.status == "available",
        )
        .order_by(ArtifactVersion.created_at.desc())
    )
    return result.scalars().first()


def _adopt_latest(artifact: Artifact, version: ArtifactVersion) -> None:
    artifact.latest_version_id = version.id
    artifact.latest_version = version


async def _insert_lineage_ignore_conflict(
    db: AsyncSession,
    *,
    project_id: str,
    input_version_id: str,
    output_version_id: str,
    created_by: str,
) -> None:
    """Insert one ``derived_from`` edge, ignoring an existing duplicate.

    Relies on ``uq_artifact_lineage_input_output``; uses ``ON CONFLICT DO NOTHING``
    on sqlite/postgresql and degrades to "select-then-insert" elsewhere.
    """
    values = {
        "id": str(uuid4()),
        "project_id": project_id,
        "input_version_id": input_version_id,
        "output_version_id": output_version_id,
        "created_by": created_by,
        "relation_type": "derived_from",
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    dialect = _dialect_name(db)
    statement = None
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as _insert

        statement = _insert(ArtifactLineage).values(**values)
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as _insert

        statement = _insert(ArtifactLineage).values(**values)
    if statement is not None:
        await db.execute(
            statement.on_conflict_do_nothing(
                index_elements=["input_version_id", "output_version_id"]
            )
        )
        return
    existing = await db.scalar(
        select(ArtifactLineage.id).where(
            ArtifactLineage.input_version_id == input_version_id,
            ArtifactLineage.output_version_id == output_version_id,
        )
    )
    if existing is None:
        db.add(
            ArtifactLineage(
                project_id=project_id,
                input_version_id=input_version_id,
                output_version_id=output_version_id,
                created_by=created_by,
                relation_type="derived_from",
            )
        )


async def _write_source_lineage(
    db: AsyncSession,
    *,
    artifact: Artifact,
    version: ArtifactVersion,
    source: ArtifactSource,
    created_by: str,
) -> None:
    """Link every ``TaskInputSnapshot`` input version to the new output version."""
    snapshot_ids = (
        await db.execute(
            select(TaskInputSnapshot.entity_id).where(
                TaskInputSnapshot.task_id == source.task_id,
                TaskInputSnapshot.entity_type == "artifact_version",
                TaskInputSnapshot.entity_id.is_not(None),
            )
        )
    ).scalars().all()

    seen: set[str] = set()
    for raw_id in snapshot_ids:
        if not raw_id:
            continue
        input_version_id = str(raw_id)
        if input_version_id == version.id or input_version_id in seen:
            continue
        seen.add(input_version_id)
        await _insert_lineage_ignore_conflict(
            db,
            project_id=artifact.project_id,
            input_version_id=input_version_id,
            output_version_id=version.id,
            created_by=created_by,
        )


async def _create_version_with_retry(
    db: AsyncSession,
    *,
    artifact: Artifact,
    filename: str,
    content_type: str | None,
    size_bytes: int,
    sha256: str,
    storage_key: str,
    storage_etag: str | None,
    manifest_json: dict[str, Any] | None,
    summary_json: dict[str, Any] | None,
    metrics_json: dict[str, Any] | None,
    validation_status: str,
    created_by: str,
    source: ArtifactSource | None,
    expires_at: datetime | None,
) -> ArtifactVersion:
    last_error: IntegrityError | None = None
    for _attempt in range(MAX_VERSION_RETRIES):
        try:
            async with db.begin_nested():
                # Row lock where supported (no-op on sqlite); keeps max+1 honest on pg.
                await db.execute(
                    select(Artifact.id)
                    .where(Artifact.id == artifact.id)
                    .with_for_update()
                )
                number = await _max_version_number(db, artifact.id) + 1
                version = ArtifactVersion(
                    artifact_id=artifact.id,
                    created_by=created_by,
                    version=number,
                    filename=filename,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    storage_key=storage_key,
                    storage_etag=storage_etag,
                    status="available",
                    validation_status=validation_status,
                    validation_errors=[],
                    manifest_json=manifest_json if manifest_json is not None else {},
                    summary_json=summary_json if summary_json is not None else {},
                    metrics_json=metrics_json if metrics_json is not None else {},
                    expires_at=expires_at,
                    source_task_id=source.task_id if source else None,
                    source_attempt_id=source.attempt_id if source else None,
                    source_tool_version_id=source.tool_version_id if source else None,
                )
                db.add(version)
                await db.flush()
            return version
        except IntegrityError as exc:
            last_error = exc
            continue
    assert last_error is not None
    raise last_error


async def attach_version_files(
    db: AsyncSession,
    *,
    version: ArtifactVersion,
    files: Sequence[tuple[str, str, bool]],
) -> list[str]:
    """Attach ``role -> file`` rows to ``version``, skipping roles that already exist.

    ``files`` items are ``(role, file_id, is_primary)`` and ``sort_order`` follows the
    given order.  An idempotent replay (same producing task, same bytes) re-derives the
    same role set for a version that already exists; writing those rows again would
    violate ``uq_artifact_version_files_version_role``, so already-present roles are
    skipped rather than raised on.  Returns the roles actually written.
    """
    if not files:
        return []
    existing = set(
        (
            await db.execute(
                select(ArtifactVersionFile.role).where(
                    ArtifactVersionFile.artifact_version_id == version.id
                )
            )
        )
        .scalars()
        .all()
    )
    written: list[str] = []
    for sort_order, (role, file_id, is_primary) in enumerate(files):
        if role in existing:
            continue
        db.add(
            ArtifactVersionFile(
                artifact_version_id=version.id,
                role=role,
                file_id=file_id,
                is_primary=is_primary,
                sort_order=sort_order,
            )
        )
        existing.add(role)
        written.append(role)
    if written:
        await db.flush()
    return written


async def upsert_version(
    db: AsyncSession,
    *,
    artifact: Artifact,
    filename: str,
    content_type: str | None,
    size_bytes: int,
    sha256: str,
    storage_key: str,
    storage_etag: str | None = None,
    manifest_json: dict[str, Any] | None = None,
    summary_json: dict[str, Any] | None = None,
    metrics_json: dict[str, Any] | None = None,
    validation_status: str = "passed",
    created_by: str,
    source: ArtifactSource | None = None,
    expires_at: datetime | None = None,
) -> tuple[ArtifactVersion, bool]:
    """Write an available ArtifactVersion for ``artifact`` and record where it came from.

    Idempotency is scoped to a *single producing task*: when the same ``source.task_id``
    is replayed/retried with the same ``sha256``, the existing version is returned with
    ``created=False`` and no duplicate lineage is written.  A *different* task producing
    identical bytes still gets its own version row (own ``source_task_id`` and its own
    lineage edges) - every production run must leave a trace - and it reuses the existing
    row's ``storage_key`` so the bytes are not stored twice.  Upload paths
    (``source is None`` / ``source.task_id is None``) keep the historical content-dedup
    semantics: an existing available version with the same ``sha256`` is reused.

    Returns ``(version, created)``.
    """
    existing = await _find_available_version_by_sha(
        db, artifact_id=artifact.id, sha256=sha256
    )
    if existing is not None:
        is_same_task = (
            source is not None
            and source.task_id is not None
            and existing.source_task_id == source.task_id
        )
        is_upload_dedup = source is None or source.task_id is None
        if is_same_task or is_upload_dedup:
            _adopt_latest(artifact, existing)
            await db.flush()
            return existing, False
        # Different producing task with identical bytes: keep a distinct version row,
        # but point it at the already-stored blob instead of writing a second copy.
        storage_key = existing.storage_key
        storage_etag = existing.storage_etag or storage_etag

    version = await _create_version_with_retry(
        db,
        artifact=artifact,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        storage_key=storage_key,
        storage_etag=storage_etag,
        manifest_json=manifest_json,
        summary_json=summary_json,
        metrics_json=metrics_json,
        validation_status=validation_status,
        created_by=created_by,
        source=source,
        expires_at=expires_at,
    )

    _adopt_latest(artifact, version)
    if source is not None and source.task_id and not artifact.source_task_id:
        artifact.source_task_id = source.task_id
    await db.flush()

    if source is not None and source.task_id:
        await _write_source_lineage(
            db, artifact=artifact, version=version, source=source, created_by=created_by
        )

    return version, True
