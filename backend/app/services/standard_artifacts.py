"""Persist parsed standard result.v2 outputs as logical ArtifactVersions."""

from __future__ import annotations

import mimetypes
from inspect import isawaitable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.artifact_standards.registry import (
    StandardArtifactRegistryError,
    get_standard_artifact_spec,
    parse_standard_ref,
    validate_relation_type,
)
from app.execution.result_parser import ParsedStandardArtifact, ParsedStandardFile, ParsedStandardResult
from app.execution.standard_contracts import (
    DeclaredArtifactOutput,
    StandardExecutionContractError,
    StandardExecutionResult,
    iter_declared_output_artifacts,
)
from app.models.artifacts import Artifact, ArtifactLineage, ArtifactVersion, ArtifactVersionFile
from app.models.files import File as FileModel, FileSourceType
from app.models.tasks import Task
from app.tool_packages.schemas import ToolPackageV2Manifest


class StandardArtifactPersistenceError(ValueError):
    """Raised when parsed standard outputs cannot be persisted."""


@dataclass(frozen=True)
class StandardArtifactPersistenceResult:
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
    result_payload = _standard_result_payload(output_result)
    if result_payload is None:
        return None

    manifest = _tool_package_v2_manifest_from_config(tool_version_config)
    if manifest is None:
        return None

    declared_outputs = [
        DeclaredArtifactOutput(
            name=item.name,
            type=item.type,
            cardinality=item.cardinality,
            required=item.required,
        )
        for item in manifest.artifacts.outputs
    ]
    parsed_result, file_records_by_path = await _parse_collected_standard_result(
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
        "artifact_version_ids_by_ref": dict(persistence_result.artifact_version_ids_by_ref),
        "file_ids_by_artifact_ref": dict(persistence_result.file_ids_by_artifact_ref),
    }


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
    file_ids_by_ref: dict[str, list[str]] = {}
    for artifact in parsed_result.artifacts:
        ref_key, version_id, file_ids = await _persist_artifact(
            db,
            task=task,
            project_id=project_id,
            user_id=user_id,
            artifact=artifact,
            file_record_resolver=file_record_resolver,
        )
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
        artifact_version_ids_by_ref=refs,
        file_ids_by_artifact_ref=file_ids_by_ref,
    )


def _standard_result_payload(output_result: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(output_result, dict):
        return None
    nested = output_result.get("result")
    if isinstance(nested, dict) and nested.get("result_version") == "aidd.sciminer/result.v2":
        return nested
    if output_result.get("result_version") == "aidd.sciminer/result.v2":
        return output_result
    return None


def _tool_package_v2_manifest_from_config(config: dict[str, Any]) -> ToolPackageV2Manifest | None:
    if not isinstance(config, dict):
        return None
    manifest_data = config.get("tool_package_manifest")
    tool_package_config = config.get("tool_package")
    if not isinstance(manifest_data, dict) and isinstance(tool_package_config, dict):
        manifest_data = tool_package_config.get("manifest")
    if not isinstance(manifest_data, dict):
        return None
    if manifest_data.get("api_version") != "aidd.sciminer/tool-package.v2":
        return None
    try:
        return ToolPackageV2Manifest.model_validate(manifest_data)
    except ValidationError as exc:
        raise StandardArtifactPersistenceError(
            f"Invalid Tool Package v2 manifest for standard result: {exc}"
        ) from exc


async def _parse_collected_standard_result(
    db: AsyncSession,
    *,
    result_payload: dict[str, Any],
    declared_outputs: list[DeclaredArtifactOutput],
    output_file_ids: list[str],
) -> tuple[ParsedStandardResult, dict[str, FileModel]]:
    try:
        standard_result = StandardExecutionResult.model_validate(result_payload)
        output_artifacts = list(iter_declared_output_artifacts(standard_result, declared_outputs))
    except (ValidationError, StandardExecutionContractError) as exc:
        raise StandardArtifactPersistenceError(f"Invalid standard result.v2 output: {exc}") from exc

    if not output_file_ids:
        raise StandardArtifactPersistenceError("Standard result.v2 produced no collected output files")

    records = (
        await db.execute(select(FileModel).where(FileModel.id.in_(output_file_ids)))
    ).scalars().all()
    file_records_by_path = _index_collected_file_records(records)
    parsed_artifacts = []
    for declaration, index, artifact in output_artifacts:
        parsed_files = {}
        for role, file_ref in artifact.files.items():
            file_record = _file_record_for_result_path(file_records_by_path, file_ref.path)
            declared_sha = str(file_ref.sha256).lower()
            actual_sha = str(file_record.sha256).lower()
            if actual_sha != declared_sha:
                raise StandardArtifactPersistenceError(
                    f"Collected file checksum mismatch for {file_ref.path}: "
                    f"declared {declared_sha}, actual {actual_sha}"
                )
            parsed_files[role] = ParsedStandardFile(
                role=role,
                path=Path(str(file_record.storage_path)),
                relative_path=file_ref.path,
                sha256=actual_sha,
                content_type=file_ref.content_type or file_record.content_type,
            )
        parsed_artifacts.append(
            ParsedStandardArtifact(
                output_name=declaration.name,
                type=artifact.type,
                name=artifact.name,
                files=parsed_files,
                index=index,
                metadata=artifact.metadata,
                summary=artifact.summary,
                metrics=artifact.metrics,
            )
        )

    return (
        ParsedStandardResult(
            artifacts=parsed_artifacts,
            relations=[relation.model_dump(by_alias=True) for relation in standard_result.relations],
            summary=standard_result.summary,
            metrics=standard_result.metrics,
        ),
        file_records_by_path,
    )


def _index_collected_file_records(records: list[FileModel]) -> dict[str, FileModel]:
    indexed = {}
    for record in records:
        file_meta = record.file_meta if isinstance(record.file_meta, dict) else {}
        relative_path = file_meta.get("relative_path")
        if isinstance(relative_path, str) and relative_path:
            indexed[relative_path] = record
        indexed[str(record.filename)] = record
    return indexed


def _file_record_for_result_path(
    file_records_by_path: dict[str, FileModel],
    result_path: str,
) -> FileModel:
    file_record = file_records_by_path.get(result_path)
    if file_record is None:
        file_record = file_records_by_path.get(result_path.replace("/", "__"))
    if file_record is None:
        raise StandardArtifactPersistenceError(
            f"Collected output file not found for standard path: {result_path}"
        )
    return file_record


async def _persist_artifact(
    db: AsyncSession,
    *,
    task: Task,
    project_id: str,
    user_id: str,
    artifact: ParsedStandardArtifact,
    file_record_resolver: FileRecordResolver | None,
) -> tuple[str, str, list[str]]:
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

    artifact_record = Artifact(
        project_id=project_id,
        created_by=user_id,
        artifact_type=standard_ref.type,
        semantic_type=standard_ref.type,
        standard_type=standard_ref.type,
        standard_version=standard_ref.version,
        name=artifact.name or _artifact_ref_key(artifact),
        source_task_id=str(task.id),
    )
    db.add(artifact_record)
    await db.flush()

    file_records: list[FileModel] = []
    for role, parsed_file in artifact.files.items():
        file_record = await _resolve_file_record(
            task=task,
            project_id=project_id,
            standard_artifact=artifact,
            role=role,
            parsed_file=parsed_file,
            file_record_resolver=file_record_resolver,
        )
        file_records.append(file_record)
    db.add_all(file_records)
    await db.flush()

    primary_file_record = file_records[
        next(
            (
                index
                for index, record in enumerate(file_records)
                if record.file_meta.get("standard_artifact_role") == primary_file.role
            ),
            0,
        )
    ]
    version = ArtifactVersion(
        artifact_id=artifact_record.id,
        created_by=user_id,
        version=1,
        filename=primary_file_record.filename,
        content_type=primary_file_record.content_type,
        size_bytes=primary_file_record.size_bytes,
        sha256=primary_file_record.sha256,
        storage_key=primary_file_record.storage_path,
        status="available",
        validation_status="passed",
        validation_errors=[],
        manifest_json=_manifest_for_artifact(artifact),
        summary_json=artifact.summary,
        metrics_json=artifact.metrics,
    )
    db.add(version)
    await db.flush()

    for sort_order, file_record in enumerate(file_records):
        role = str(file_record.file_meta.get("standard_artifact_role"))
        db.add(
            ArtifactVersionFile(
                artifact_version_id=version.id,
                role=role,
                file_id=file_record.id,
                is_primary=role == primary_file.role,
                sort_order=sort_order,
            )
        )

    artifact_record.latest_version_id = version.id
    artifact_record.latest_version = version
    await db.flush()
    return _artifact_ref_key(artifact), version.id, [file.id for file in file_records]


async def _resolve_file_record(
    *,
    task: Task,
    project_id: str,
    standard_artifact: ParsedStandardArtifact,
    role: str,
    parsed_file: ParsedStandardFile,
    file_record_resolver: FileRecordResolver | None,
) -> FileModel:
    if file_record_resolver is None:
        return _file_record_for_standard_file(
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


def _file_record_for_standard_file(
    *,
    task: Task,
    project_id: str,
    standard_artifact: ParsedStandardArtifact,
    role: str,
    parsed_file: ParsedStandardFile,
) -> FileModel:
    file_path = Path(parsed_file.path)
    return _annotate_file_record(
        FileModel(
            project_id=project_id,
            owner_id=task.user_id,
            filename=file_path.name,
            content_type=parsed_file.content_type
            or mimetypes.guess_type(file_path.name)[0]
            or "application/octet-stream",
            size_bytes=file_path.stat().st_size,
            sha256=parsed_file.sha256,
            storage_path=str(file_path),
            source_type=FileSourceType.TOOL_OUTPUT.value,
            is_public=False,
            is_permanent=False,
        ),
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


def _manifest_for_artifact(artifact: ParsedStandardArtifact) -> dict[str, Any]:
    return {
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


def _artifact_ref_key(artifact: ParsedStandardArtifact) -> str:
    if artifact.index is None:
        return artifact.output_name
    return f"{artifact.output_name}[{artifact.index}]"


def _task_project_id(task: Task) -> str:
    data = task.extra_data if isinstance(task.extra_data, dict) else {}
    project_id = data.get("project_id")
    if not project_id:
        raise StandardArtifactPersistenceError(
            "Task extra_data.project_id is required for standard artifacts"
        )
    return str(project_id)
