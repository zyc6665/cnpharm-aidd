"""Legacy remote API request helpers."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LegacyInputFileStagePlan:
    source_path: str
    destination_path: str


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


def legacy_input_file_stage_plan(file_record: Any, input_dir: str) -> LegacyInputFileStagePlan:
    source_path = str(file_record.storage_path or "")
    if not source_path or not os.path.exists(source_path):
        raise ValueError(f"Input file {file_record.filename} not found in storage")
    return LegacyInputFileStagePlan(
        source_path=source_path,
        destination_path=os.path.join(input_dir, file_record.filename),
    )


def flatten_legacy_remote_api_params(data: dict[str, Any]) -> dict[str, str]:
    return {
        key: json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        for key, value in data.items()
    }


def legacy_output_filename(file_info: dict[str, Any], fallback_filename: str) -> str:
    return str(file_info.get("name") or file_info.get("filename") or fallback_filename)


def legacy_output_file_record_data(
    *,
    filename: str,
    content_type: str,
    content: bytes,
    owner_id: str | None,
) -> dict[str, Any]:
    return {
        "filename": filename,
        "content_type": content_type,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "source_type": "tool_output",
        "owner_id": owner_id,
        "is_public": False,
        "is_permanent": False,
    }
