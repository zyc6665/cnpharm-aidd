"""Legacy remote API request helpers."""

from __future__ import annotations

import json
from typing import Any


def build_legacy_remote_api_request_data(
    *,
    task_id: str,
    input_params: dict[str, Any],
    input_file_paths: list[str] | None = None,
) -> dict[str, Any]:
    if "params" in input_params and "input_files" in input_params:
        request_data: dict[str, Any] = {
            "task_id": task_id,
            "params": input_params["params"],
            "input_files": input_params["input_files"],
        }
    else:
        request_data = {"task_id": task_id, "params": input_params}

    if input_file_paths:
        request_data["files"] = input_file_paths
    return request_data


def flatten_legacy_remote_api_params(data: dict[str, Any]) -> dict[str, str]:
    return {
        key: json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        for key, value in data.items()
    }
