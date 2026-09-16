"""Remote tool result and status protocol helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


class RemoteToolResultError(ValueError):
    """Raised when a remote tool result payload is invalid."""


@dataclass(frozen=True)
class RemoteStatusState:
    value: str
    message: str
    progress: float | None
    is_success: bool
    can_poll: bool
    error_message: str | None


def remote_status_message(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    error = payload.get("error")
    if isinstance(error, dict):
        error_message = error.get("message")
        if isinstance(error_message, str) and error_message.strip():
            return error_message.strip()
    if isinstance(error, str) and error.strip():
        return error.strip()
    return "Remote tool run status updated"


def remote_status_progress(payload: dict[str, Any], status_value: str) -> float | None:
    raw_progress = payload.get("progress")
    if isinstance(raw_progress, (int, float)):
        return float(max(0, min(100, raw_progress)))
    if status_value == "success":
        return 100.0
    return None


def remote_status_state(payload: dict[str, Any]) -> RemoteStatusState:
    status_value = str(payload.get("status") or "").lower()
    message = remote_status_message(payload)
    progress = remote_status_progress(payload, status_value)
    error_message: str | None = None
    if status_value == "failure":
        error_message = message
    elif status_value == "canceled":
        error_message = "Remote tool run was canceled"
    elif status_value not in {"queued", "running", "success"}:
        error_message = f"Unsupported remote run status: {status_value}"
    return RemoteStatusState(
        value=status_value,
        message=message,
        progress=progress,
        is_success=status_value == "success",
        can_poll=status_value in {"queued", "running"},
        error_message=error_message,
    )


def iter_remote_log_messages(payload: dict[str, Any]) -> Iterator[str]:
    items = payload.get("items")
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        message = item.get("message")
        if isinstance(message, str) and message.strip():
            yield message.strip()


def remote_log_next_cursor(payload: dict[str, Any], cursor: str | None) -> str | None:
    return payload.get("next_cursor") or cursor


def remote_artifacts_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RemoteToolResultError("Remote artifacts response must be an object")
    if payload.get("result_version") != "aidd.sciminer/result.v2":
        raise RemoteToolResultError("Remote artifacts response must be result.v2")
    return payload


def remote_result_filename(file_ref: dict[str, Any], role: str) -> str:
    explicit_name = file_ref.get("filename") or file_ref.get("name")
    if isinstance(explicit_name, str) and explicit_name.strip():
        return Path(explicit_name).name
    path = file_ref.get("path")
    if isinstance(path, str) and Path(path).name:
        return Path(path).name
    return f"{role}.dat"


def verify_remote_result_file_checksum(
    file_ref: dict[str, Any],
    role: str,
    content: bytes,
) -> str:
    actual_sha256 = hashlib.sha256(content).hexdigest()
    declared_sha256 = str(file_ref.get("sha256") or "").lower()
    if declared_sha256 and actual_sha256 != declared_sha256:
        result_path = file_ref.get("path") or role
        raise RemoteToolResultError(
            f"Remote result file checksum mismatch for {result_path}: "
            f"declared {declared_sha256}, actual {actual_sha256}"
        )
    return actual_sha256


def remote_result_file_record_data(
    *,
    file_ref: dict[str, Any],
    artifact_ref: str,
    artifact: dict[str, Any],
    role: str,
    content_length: int,
    sha256: str,
    owner_id: str | None,
) -> dict[str, Any]:
    return {
        "filename": remote_result_filename(file_ref, role),
        "content_type": file_ref.get("content_type") or "application/octet-stream",
        "size_bytes": content_length,
        "sha256": sha256,
        "storage_path": "pending",
        "source_type": "tool_output",
        "owner_id": owner_id,
        "is_public": False,
        "is_permanent": False,
        "file_meta": {
            "remote_result_path": file_ref.get("path"),
            "relative_path": file_ref.get("path"),
            "artifact_ref": artifact.get("ref"),
            "standard_artifact_output": artifact_ref,
            "file_role": role,
        },
    }


def iter_remote_result_artifacts(raw_artifacts: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(raw_artifacts, list):
        for index, artifact in enumerate(raw_artifacts):
            if isinstance(artifact, dict):
                yield str(artifact.get("ref") or artifact.get("name") or index), artifact
        return
    if isinstance(raw_artifacts, dict):
        for artifact_ref, artifact in raw_artifacts.items():
            if isinstance(artifact, list):
                for index, item in enumerate(artifact):
                    if isinstance(item, dict):
                        yield f"{artifact_ref}[{index}]", item
            elif isinstance(artifact, dict):
                yield str(artifact_ref), artifact
