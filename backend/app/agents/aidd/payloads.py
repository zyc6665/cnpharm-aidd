"""Build TaskCreate-compatible payloads for agent steps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.aidd.capabilities import ToolCapability


@dataclass(frozen=True)
class AgentTaskPayload:
    params: dict[str, Any]
    file_ids: list[str]


def assign_dotted(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = target
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[parts[-1]] = value


def _runtime_file_field(executor_type: str, field: str) -> str:
    if executor_type == "ssh_job" and not field.startswith("input_files."):
        return f"input_files.{field}"
    return field


def build_agent_task_payload(
    *,
    capability: ToolCapability,
    executor_type: str,
    semantic_files: dict[str, dict[str, str]],
    step_params: dict[str, Any],
) -> AgentTaskPayload:
    params: dict[str, Any] = {}
    file_ids: list[str] = []

    for key, value in {**capability.defaults, **step_params}.items():
        assign_dotted(params, key, value)

    for input_binding in capability.inputs:
        semantic_file = semantic_files.get(input_binding.semantic_type)
        if not semantic_file:
            if input_binding.required:
                raise ValueError(
                    f"Missing required semantic input: {input_binding.semantic_type}"
                )
            continue

        file_ids.append(semantic_file["file_id"])
        if executor_type == "ssh_job":
            field_value = f"input/{semantic_file['filename']}"
        else:
            field_value = semantic_file["download_url"]

        assign_dotted(params, _runtime_file_field(executor_type, input_binding.field), field_value)

    return AgentTaskPayload(params=params, file_ids=list(dict.fromkeys(file_ids)))
