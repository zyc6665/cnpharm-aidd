"""Persist parsed standard result.v2 outputs as logical ArtifactVersions."""

from __future__ import annotations

import mimetypes
from inspect import isawaitable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.artifact_standards.registry import (
    StandardArtifactRegistryError,
    get_standard_artifact_spec,
    parse_standard_ref,
    validate_relation_type,
)
from app.execution.result_parser import (
    ParsedStandardArtifact,
    ParsedStandardFile,
    ParsedStandardResult,
)
from app.models.artifacts import ArtifactLineage
from app.models.files import File as FileModel, FileSourceType
from app.models.tasks import Task
from app.common.task_context import task_project_id
from app.files.writer import store_file_path
from app.services.artifact_identity import resolve_identity_full
from app.services.artifact_writer import (
    ArtifactSource,
    attach_version_files,
    upsert_artifact,
    upsert_version,
)
from app.services.standard_artifact_collection import (
    collected_standard_result_payload,
    declared_standard_outputs_from_config,
    parse_collected_standard_result,
)
from app.services.standard_artifact_errors import StandardArtifactPersistenceError


@dataclass(frozen=True)
class StandardArtifactPersistenceResult:
    artifact_ids_by_ref: dict[str, str] = field(default_factory=dict)
    artifact_version_ids_by_ref: dict[str, str] = field(default_factory=dict)
    file_ids_by_artifact_ref: dict[str, list[str]] = field(default_factory=dict)


FileRecordResolver = Callable[
    [ParsedStandardArtifact, str, ParsedStandardFile],
    FileModel | Awaitable[FileModel],
]


async def create_artifact_versions_from_collected_result(
    db: AsyncSession,
    *,
    task: Task,
    tool_version_config: dict[str, Any],
    output_result: dict[str, Any],
    output_file_ids: list[str],
) -> StandardArtifactPersistenceResult | None:
    """Persist collected result.v2 outputs when the tool declares a v2 package contract."""
    result_payload = collected_standard_result_payload(output_result)
    if result_payload is None:
        return None

    declared_outputs = declared_standard_outputs_from_config(tool_version_config)
    if not declared_outputs:
        return None
    parsed_result, file_records_by_path = await parse_collected_standard_result(
        db,
        result_payload=result_payload,
        declared_outputs=declared_outputs,
        output_file_ids=output_file_ids,
    )

    def resolve_file(_artifact: ParsedStandardArtifact, _role: str, parsed_file: ParsedStandardFile):
        return file_records_by_path[parsed_file.relative_path]

    return await create_artifact_versions_from_parsed_result(
        db,
        task=task,
        parsed_result=parsed_result,
        file_record_resolver=resolve_file,
    )


def standard_artifact_result_summary(
    persistence_result: StandardArtifactPersistenceResult,
) -> dict[str, Any]:
    """Serialize standard persistence metadata into legacy TaskOutput.result."""
    return {
        "artifact_ids_by_ref": dict(persistence_result.artifact_ids_by_ref),
        "artifact_version_ids_by_ref": dict(persistence_result.artifact_version_ids_by_ref),
        "file_ids_by_artifact_ref": dict(persistence_result.file_ids_by_artifact_ref),
    }


async def persist_standard_artifacts_from_task_output(
    db: AsyncSession,
    *,
    task: Task,
    tool_version_config: dict[str, Any],
    output_result: dict[str, Any],
    output_file_ids: list[str],
) -> StandardArtifactPersistenceResult | None:
    """Persist standard result.v2 outputs collected for a task, if present."""
    return await create_artifact_versions_from_collected_result(
        db,
        task=task,
        tool_version_config=tool_version_config,
        output_result=output_result,
        output_file_ids=output_file_ids,
    )


def attach_standard_artifact_summary(
    output_result: dict[str, Any],
    persistence_result: StandardArtifactPersistenceResult,
) -> dict[str, Any]:
    """Attach persisted standard ArtifactVersion IDs without mutating the original result."""
    result = dict(output_result)
    result["standard_artifacts"] = standard_artifact_result_summary(persistence_result)
    return result


async def create_artifact_versions_from_parsed_result(
    db: AsyncSession,
    *,
    task: Task,
    parsed_result: ParsedStandardResult,
    file_record_resolver: FileRecordResolver | None = None,
) -> StandardArtifactPersistenceResult:
    """Persist standard output Artifacts and controlled relations for a task."""
    project_id = _task_project_id(task)
    user_id = str(task.user_id or "")
    if not user_id:
        raise StandardArtifactPersistenceError("Task user_id is required for standard artifacts")

    refs: dict[str, str] = {}
    artifact_ids_by_ref: dict[str, str] = {}
    file_ids_by_ref: dict[str, list[str]] = {}
    for artifact in parsed_result.artifacts:
        ref_key, artifact_id, version_id, file_ids = await _persist_artifact(
            db,
            task=task,
            project_id=project_id,
            user_id=user_id,
            artifact=artifact,
            file_record_resolver=file_record_resolver,
        )
        artifact_ids_by_ref[ref_key] = artifact_id
        refs[ref_key] = version_id
        file_ids_by_ref[ref_key] = file_ids

    for relation in parsed_result.relations:
        try:
            relation_type = validate_relation_type(str(relation.get("type") or ""))
        except StandardArtifactRegistryError as exc:
            raise StandardArtifactPersistenceError(str(exc)) from exc

        from_ref = str(relation.get("from") or relation.get("from_ref") or "")
        to_ref = str(relation.get("to") or "")
        if from_ref not in refs or to_ref not in refs:
            raise StandardArtifactPersistenceError(
                f"Relation references unknown artifact: {from_ref} -> {to_ref}"
            )
        existing_lineage = await db.scalar(
            select(ArtifactLineage.id).where(
                ArtifactLineage.input_version_id == refs[from_ref],
                ArtifactLineage.output_version_id == refs[to_ref],
            )
        )
        if existing_lineage is not None:
            # 同一任务重放会复用同一批版本；受控关系边必须保持幂等，
            # 否则 uq_artifact_lineage_input_output 会直接冲突。
            continue
        db.add(
            ArtifactLineage(
                project_id=project_id,
                input_version_id=refs[from_ref],
                output_version_id=refs[to_ref],
                created_by=user_id,
                relation_type=relation_type,
            )
        )

    await db.flush()
    return StandardArtifactPersistenceResult(
        artifact_ids_by_ref=artifact_ids_by_ref,
        artifact_version_ids_by_ref=refs,
        file_ids_by_artifact_ref=file_ids_by_ref,
    )


async def _persist_artifact(
    db: AsyncSession,
    *,
    task: Task,
    project_id: str,
    user_id: str,
    artifact: ParsedStandardArtifact,
    file_record_resolver: FileRecordResolver | None,
) -> tuple[str, str, str, list[str]]:
    try:
        standard_ref = parse_standard_ref(artifact.type)
    except StandardArtifactRegistryError as exc:
        raise StandardArtifactPersistenceError(str(exc)) from exc

    spec = get_standard_artifact_spec(standard_ref.ref)
    primary_role = next((role.role for role in spec.file_roles if role.primary), None)
    primary_file = (
        artifact.files.get(primary_role)
        if primary_role
        else next(iter(artifact.files.values()), None)
    )
    if primary_file is None:
        raise StandardArtifactPersistenceError(
            f"Artifact {artifact.output_name} has no files to persist"
        )

    # Artifact 是逻辑资产的「身份」，版本才是每次运行的记录。走统一写入点按稳定标识
    # 取或建，避免同一任务重试/重放时每次都新建一个资产根。按 name 参与身份判据，
    # 因为一次运行可能产出多个同类型、不同名字的资产（如多个配体）。
    # 三列身份统一由解析器给出，标准产物三列都收敛到标准 type，版本只走 standard_version。
    resolved_type, resolved_semantic, resolved_standard, resolved_version = resolve_identity_full(
        standard_ref.type,
        standard_type=standard_ref.type,
        standard_version=standard_ref.version,
    )
    artifact_record, _artifact_created = await upsert_artifact(
        db,
        project_id=project_id,
        artifact_type=resolved_type,
        semantic_type=resolved_semantic,
        standard_type=resolved_standard,
        standard_version=resolved_version,
        name=artifact.name or _artifact_ref_key(artifact),
        created_by=user_id,
        match_name=True,
    )

    resolved_files: list[tuple[str, FileModel]] = []
    for role, parsed_file in artifact.files.items():
        file_record = await _resolve_file_record(
            db=db,
            task=task,
            project_id=project_id,
            standard_artifact=artifact,
            role=role,
            parsed_file=parsed_file,
            file_record_resolver=file_record_resolver,
        )
        resolved_files.append((role, file_record))
    file_records = list(dict.fromkeys(file_record for _, file_record in resolved_files))
    db.add_all(file_records)
    await db.flush()

    primary_file_record = next(
        (
            file_record
            for role, file_record in resolved_files
            if role == primary_file.role
        ),
        file_records[0],
    )
    attempt_id = (task.extra_data or {}).get("execution_attempt_id")
    version, _created = await upsert_version(
        db,
        artifact=artifact_record,
        filename=primary_file_record.filename,
        content_type=primary_file_record.content_type,
        size_bytes=primary_file_record.size_bytes,
        sha256=primary_file_record.sha256,
        storage_key=primary_file_record.storage_path,
        manifest_json=_manifest_for_artifact(
            artifact,
            mock=bool((task.extra_data or {}).get("mock")),
        ),
        summary_json=artifact.summary,
        metrics_json=artifact.metrics,
        validation_status="passed",
        created_by=user_id,
        source=ArtifactSource(
            task_id=str(task.id),
            attempt_id=str(attempt_id) if attempt_id else None,
            tool_version_id=str(task.tool_version_id) if task.tool_version_id else None,
        ),
    )

    # Route through the writer so an idempotent replay (same task, same bytes) cannot
    # re-write roles that already exist on the reused version.
    await attach_version_files(
        db,
        version=version,
        files=[
            (role, file_record.id, role == primary_file.role)
            for role, file_record in resolved_files
        ],
    )

    await db.flush()
    return (
        _artifact_ref_key(artifact),
        artifact_record.id,
        version.id,
        [file.id for file in file_records],
    )


async def _resolve_file_record(
    *,
    db: AsyncSession,
    task: Task,
    project_id: str,
    standard_artifact: ParsedStandardArtifact,
    role: str,
    parsed_file: ParsedStandardFile,
    file_record_resolver: FileRecordResolver | None,
) -> FileModel:
    if file_record_resolver is None:
        return await _file_record_for_standard_file(
            db=db,
            task=task,
            project_id=project_id,
            standard_artifact=standard_artifact,
            role=role,
            parsed_file=parsed_file,
        )
    resolved = file_record_resolver(standard_artifact, role, parsed_file)
    file_record = await resolved if isawaitable(resolved) else resolved
    return _annotate_file_record(
        file_record,
        task=task,
        project_id=project_id,
        standard_artifact=standard_artifact,
        role=role,
        parsed_file=parsed_file,
    )


async def _file_record_for_standard_file(
    *,
    db: AsyncSession,
    task: Task,
    project_id: str,
    standard_artifact: ParsedStandardArtifact,
    role: str,
    parsed_file: ParsedStandardFile,
) -> FileModel:
    file_path = Path(parsed_file.path)
    file_record = await store_file_path(
        db,
        source_path=file_path,
        filename=file_path.name,
        content_type=(
            parsed_file.content_type
            or mimetypes.guess_type(file_path.name)[0]
            or "application/octet-stream"
        ),
        source_type=FileSourceType.TOOL_OUTPUT,
        owner_id=task.user_id,
        project_id=project_id,
        size_bytes=file_path.stat().st_size,
        sha256=parsed_file.sha256,
    )
    return _annotate_file_record(
        file_record,
        task=task,
        project_id=project_id,
        standard_artifact=standard_artifact,
        role=role,
        parsed_file=parsed_file,
    )


def _annotate_file_record(
    file_record: FileModel,
    *,
    task: Task,
    project_id: str,
    standard_artifact: ParsedStandardArtifact,
    role: str,
    parsed_file: ParsedStandardFile,
) -> FileModel:
    file_meta = dict(file_record.file_meta or {})
    file_meta.update(
        {
            "standard_artifact_ref": standard_artifact.type,
            "standard_artifact_output": standard_artifact.output_name,
            "standard_artifact_index": standard_artifact.index,
            "standard_artifact_role": role,
            "relative_path": parsed_file.relative_path,
            "source_task_id": str(task.id),
        }
    )
    file_record.file_meta = file_meta
    if not file_record.project_id:
        file_record.project_id = project_id
    if not file_record.owner_id:
        file_record.owner_id = task.user_id
    return file_record


def _manifest_for_artifact(
    artifact: ParsedStandardArtifact,
    *,
    mock: bool = False,
) -> dict[str, Any]:
    manifest = {
        "type": artifact.type,
        "name": artifact.name,
        "output_name": artifact.output_name,
        "index": artifact.index,
        "files": {
            role: {
                "relative_path": parsed_file.relative_path,
                "sha256": parsed_file.sha256,
                "content_type": parsed_file.content_type,
            }
            for role, parsed_file in artifact.files.items()
        },
        "metadata": artifact.metadata,
    }
    if mock:
        manifest["mock"] = True
    return manifest


def _artifact_ref_key(artifact: ParsedStandardArtifact) -> str:
    if artifact.index is None:
        return artifact.output_name
    return f"{artifact.output_name}[{artifact.index}]"


def _task_project_id(task: Task) -> str:
    project_id = task_project_id(task)
    if not project_id:
        raise StandardArtifactPersistenceError(
            "Task extra_data.project_id is required for standard artifacts"
        )
    return str(project_id)
