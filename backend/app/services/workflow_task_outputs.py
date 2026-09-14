"""Workflow task output state helpers."""

from __future__ import annotations

from typing import Any

from app.models.tasks import Task
from app.services.workflow_artifacts import standard_artifact_file_ids


def task_project_id(task: Task) -> str | None:
    data = task.extra_data if isinstance(task.extra_data, dict) else {}
    project_id = data.get("project_id")
    return str(project_id) if project_id else None


def has_required_declared_standard_outputs(declared_outputs: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(declaration, dict)
        and bool(declaration.get("name"))
        and declaration.get("required", True) is not False
        for declaration in declared_outputs
    )


def workflow_output_file_ids(
    *,
    semantic_outputs: dict[str, dict[str, Any]],
    standard_artifacts: dict[str, Any],
    declared_artifact_outputs: list[dict[str, Any]],
) -> list[str]:
    output_file_ids = [
        str(value["file_id"])
        for value in semantic_outputs.values()
        if value.get("source") == "output_files" and value.get("file_id")
    ]
    for declaration in declared_artifact_outputs:
        if not isinstance(declaration, dict) or not declaration.get("name"):
            continue
        output_file_ids.extend(
            standard_artifact_file_ids(standard_artifacts, str(declaration["name"]))
        )
    return list(dict.fromkeys(output_file_ids))
