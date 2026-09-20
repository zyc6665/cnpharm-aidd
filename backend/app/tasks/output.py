"""Shared task output normalization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.execution.contracts import ProducedArtifact
from app.tasks.naming import _extract_file_ids_from_result


def extract_output_file_ids(output_result: dict[str, Any]) -> list[str]:
    """Extract and deduplicate file IDs from an executor result."""
    return _extract_file_ids_from_result(output_result, dedupe=True, skip_empty=True)


def prepare_task_output(output_result: dict[str, Any]) -> dict[str, Any]:
    """Normalize executor output for TaskOutput persistence."""
    file_ids = extract_output_file_ids(output_result)
    return {
        "result": output_result,
        "file_ids": file_ids,
        "output_type": "visualization" if file_ids else "json",
    }


def execution_artifacts_to_task_result(
    artifacts: Iterable[ProducedArtifact | Mapping[str, Any]],
) -> dict[str, Any]:
    """Convert ExecutionPort artifacts into the shared task result shape."""
    output_files: list[dict[str, Any]] = []
    output_file_ids: list[str] = []
    for artifact in artifacts:
        normalized = (
            artifact
            if isinstance(artifact, ProducedArtifact)
            else ProducedArtifact.model_validate(artifact)
        )
        output_files.append(normalized.model_dump(mode="json", exclude_none=True))
        if normalized.file_id:
            output_file_ids.append(str(normalized.file_id))

    return {
        "success": True,
        "output_files": output_files,
        "output_file_ids": list(dict.fromkeys(output_file_ids)),
    }


def prepare_execution_artifacts(
    artifacts: Iterable[ProducedArtifact | Mapping[str, Any]],
) -> dict[str, Any]:
    """Normalize ExecutionPort artifacts into a persistable TaskOutput payload."""
    return prepare_task_output(execution_artifacts_to_task_result(artifacts))
