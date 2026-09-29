"""Collect and validate standard result.v2 task outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select

from app.execution.result_parser import (
    ParsedStandardArtifact,
    ParsedStandardFile,
    ParsedStandardResult,
)
from app.execution.standard_contracts import (
    DeclaredArtifactOutput,
    StandardExecutionContractError,
    StandardExecutionResult,
    iter_declared_output_artifacts,
)
from app.files.file_records import is_file_usable
from app.models.files import File as FileModel
from app.services.standard_artifact_errors import (
    StandardArtifactPersistenceError,
)
from app.tool_packages.config_resolver import (
    ToolPackageConfigError,
    tool_package_v2_manifest,
)


STANDARD_RESULT_VERSION = "aidd.sciminer/result.v2"


def collected_standard_result_payload(
    output_result: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(output_result, dict):
        return None
    standard_result = output_result.get("standard_result")
    if _is_standard_result_payload(standard_result):
        return standard_result
    nested = output_result.get("result")
    if _is_standard_result_payload(nested):
        return nested
    if output_result.get("result_version") == STANDARD_RESULT_VERSION:
        return output_result
    return None


def declared_standard_outputs_from_config(
    config: dict[str, Any],
) -> list[DeclaredArtifactOutput]:
    try:
        manifest = tool_package_v2_manifest(config)
    except ToolPackageConfigError as exc:
        raise StandardArtifactPersistenceError(
            f"Invalid Tool Package v2 manifest for standard result: {exc}"
        ) from exc
    if manifest is not None:
        return [
            DeclaredArtifactOutput(
                name=item.name,
                type=item.type,
                cardinality=item.cardinality,
                required=item.required,
            )
            for item in manifest.artifacts.outputs
        ]

    if not isinstance(config, dict):
        return []
    config_type = config.get("type")
    is_non_v1_remote = (
        config_type == "remote_api"
        and config.get("mode") != "remote_tool_v1"
    )
    if is_non_v1_remote:
        return []
    if config_type not in {"remote_api", "builtin", "ssh_job", "k8s_job"}:
        return []
    artifacts = config.get("artifacts")
    raw_outputs = None
    if isinstance(artifacts, dict):
        raw_outputs = artifacts.get("outputs")
    if not isinstance(raw_outputs, list):
        return []
    return [
        DeclaredArtifactOutput(
            name=str(item.get("name")),
            type=str(item.get("type")),
            cardinality=str(item.get("cardinality") or "one"),
            required=item.get("required") is not False,
        )
        for item in raw_outputs
        if isinstance(item, dict)
    ]


async def parse_collected_standard_result(
    db: Any,
    *,
    result_payload: dict[str, Any],
    declared_outputs: list[DeclaredArtifactOutput],
    output_file_ids: list[str],
) -> tuple[ParsedStandardResult, dict[str, FileModel]]:
    try:
        standard_result = StandardExecutionResult.model_validate(
            result_payload
        )
        output_artifacts = list(
            iter_declared_output_artifacts(standard_result, declared_outputs)
        )
    except (ValidationError, StandardExecutionContractError) as exc:
        raise StandardArtifactPersistenceError(
            f"Invalid standard result.v2 output: {exc}"
        ) from exc

    if not output_file_ids:
        raise StandardArtifactPersistenceError(
            "Standard result.v2 produced no collected output files"
        )

    query = select(FileModel).where(FileModel.id.in_(output_file_ids))
    records = (await db.execute(query)).scalars().all()
    file_records_by_path = _index_collected_file_records(records)
    parsed_artifacts = []
    for declaration, index, artifact in output_artifacts:
        parsed_files = {}
        for role, file_ref in artifact.files.items():
            file_record = _file_record_for_result_path(
                file_records_by_path,
                file_ref.path,
            )
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
            relations=[
                relation.model_dump(by_alias=True)
                for relation in standard_result.relations
            ],
            summary=standard_result.summary,
            metrics=standard_result.metrics,
        ),
        file_records_by_path,
    )


def _is_standard_result_payload(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("result_version") == STANDARD_RESULT_VERSION
    )


def _index_collected_file_records(
    records: list[FileModel],
) -> dict[str, FileModel]:
    indexed = {}
    for record in records:
        if not is_file_usable(record):
            continue
        file_meta = {}
        if isinstance(record.file_meta, dict):
            file_meta = record.file_meta
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
