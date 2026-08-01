"""Parse and verify standard result.v2 envelopes emitted by tool adapters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.execution.standard_contracts import (
    DeclaredArtifactOutput,
    StandardExecutionContractError,
    StandardExecutionResult,
    StandardOutputArtifact,
    iter_declared_output_artifacts,
)


class StandardResultParserError(ValueError):
    """Raised when result.v2 cannot be parsed or verified."""


@dataclass(frozen=True)
class ParsedStandardFile:
    role: str
    path: Path
    relative_path: str
    sha256: str
    content_type: str | None = None


@dataclass(frozen=True)
class ParsedStandardArtifact:
    output_name: str
    type: str
    name: str | None
    files: dict[str, ParsedStandardFile]
    index: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedStandardResult:
    artifacts: list[ParsedStandardArtifact]
    relations: list[dict[str, Any]]
    summary: dict[str, Any]
    metrics: dict[str, Any]


def parse_standard_result(
    *,
    result_path: Path,
    output_dir: Path,
    declared_outputs: list[DeclaredArtifactOutput] | tuple[DeclaredArtifactOutput, ...],
) -> ParsedStandardResult:
    """Parse result.v2, validate declarations, and verify output files."""
    if not result_path.is_file():
        raise StandardResultParserError(f"Missing standard result: {result_path}")
    try:
        raw_result = json.loads(result_path.read_text(encoding="utf-8"))
        result = StandardExecutionResult.model_validate(raw_result)
    except json.JSONDecodeError as exc:
        raise StandardResultParserError(f"Invalid standard result JSON: {exc}") from exc
    except ValidationError as exc:
        raise StandardResultParserError(str(exc)) from exc

    try:
        artifacts = [
            _parse_artifact(
                output_name=declaration.name,
                index=index,
                artifact=artifact,
                output_dir=output_dir,
            )
            for declaration, index, artifact in iter_declared_output_artifacts(
                result,
                declared_outputs,
            )
        ]
    except StandardExecutionContractError as exc:
        raise StandardResultParserError(str(exc)) from exc

    return ParsedStandardResult(
        artifacts=artifacts,
        relations=[relation.model_dump(by_alias=True) for relation in result.relations],
        summary=result.summary,
        metrics=result.metrics,
    )


def _parse_artifact(
    *,
    output_name: str,
    index: int | None,
    artifact: StandardOutputArtifact,
    output_dir: Path,
) -> ParsedStandardArtifact:
    files = {
        role: _parse_file(role=role, file_ref=file_ref, output_dir=output_dir)
        for role, file_ref in artifact.files.items()
    }
    return ParsedStandardArtifact(
        output_name=output_name,
        type=artifact.type,
        name=artifact.name,
        files=files,
        index=index,
        metadata=artifact.metadata,
        summary=artifact.summary,
        metrics=artifact.metrics,
    )


def _parse_file(*, role: str, file_ref: Any, output_dir: Path) -> ParsedStandardFile:
    output_root = output_dir.resolve()
    file_path = (output_root / file_ref.path).resolve()
    if output_root != file_path and output_root not in file_path.parents:
        raise StandardResultParserError(f"Unsafe output path: {file_ref.path}")
    if not file_path.is_file():
        raise StandardResultParserError(f"Output file does not exist: {file_ref.path}")
    actual_sha256 = _sha256_file(file_path)
    declared_sha256 = str(file_ref.sha256).lower()
    if actual_sha256 != declared_sha256:
        raise StandardResultParserError(
            f"Output file checksum mismatch for {file_ref.path}: "
            f"declared {declared_sha256}, actual {actual_sha256}"
        )
    return ParsedStandardFile(
        role=role,
        path=file_path,
        relative_path=file_ref.path,
        sha256=actual_sha256,
        content_type=file_ref.content_type,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
