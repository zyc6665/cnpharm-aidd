"""Remote tool invocation payload helpers."""

from __future__ import annotations

from typing import Any


def remote_tool_parameters(input_params: Any) -> dict[str, Any]:
    if not isinstance(input_params, dict):
        return {}
    parameters = input_params.get("parameters")
    return parameters if isinstance(parameters, dict) else input_params


def remote_invoke_run_id(payload: dict[str, Any]) -> str:
    remote_run_id = str(payload.get("remote_run_id") or "").strip()
    if not remote_run_id:
        raise ValueError("Remote tool invoke response missing remote_run_id")
    return remote_run_id


def recorded_remote_run_id(extra_data: Any) -> str | None:
    if not isinstance(extra_data, dict):
        return None
    remote_run_id = str(extra_data.get("remote_run_id") or "").strip()
    return remote_run_id or None


def build_remote_tool_invoke_payload(
    *,
    request_id: str,
    task_id: str,
    tool_slug: str | None,
    tool_version: str | None,
    inputs: dict[str, Any],
    parameters: dict[str, Any],
    project_id: str | None,
    user_id: str | None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "task": {
            "id": task_id,
            "tool_slug": tool_slug,
            "tool_version": tool_version,
        },
        "inputs": inputs,
        "parameters": parameters,
        "context": {
            "project_id": project_id,
            "user_id": user_id,
        },
    }
