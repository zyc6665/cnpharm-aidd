"""Remote tool registration config and publish rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any

from app.remote_tools.client import RemoteToolDiscoveryResult


REMOTE_TOOL_SMOKE_REQUIRED_ERROR = "remote_tool_v1 requires successful smoke test before publish"
REMOTE_TOOL_SMOKE_HASH_MISMATCH_ERROR = (
    "remote_tool_v1 smoke test manifest hash does not match current manifest"
)


@dataclass(frozen=True)
class RemoteToolSmokeResultUpdate:
    config: dict[str, Any]
    auto_publish: bool


def is_remote_tool_v1_config(config: dict[str, Any]) -> bool:
    return config.get("type") == "remote_api" and config.get("mode") == "remote_tool_v1"


def remote_tool_publish_errors(config: dict[str, Any]) -> list[str]:
    if not is_remote_tool_v1_config(config):
        return []

    last_smoke_test = config.get("last_smoke_test")
    if not isinstance(last_smoke_test, dict):
        return [REMOTE_TOOL_SMOKE_REQUIRED_ERROR]
    if last_smoke_test.get("status") != "success":
        return [REMOTE_TOOL_SMOKE_REQUIRED_ERROR]
    if last_smoke_test.get("manifest_sha256") != config.get("manifest_sha256"):
        return [REMOTE_TOOL_SMOKE_HASH_MISMATCH_ERROR]
    return []


def build_remote_tool_smoke_result_update(
    *,
    config: dict[str, Any],
    extra_data: dict[str, Any],
    task_id: str,
    status: str,
    finished_at: datetime | None,
    output_result: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> RemoteToolSmokeResultUpdate | None:
    if extra_data.get("smoke_test") is not True:
        return None
    if extra_data.get("smoke_test_type") != "remote_tool_v1":
        return None
    if not is_remote_tool_v1_config(config):
        return None

    next_config = dict(config)
    manifest_sha256 = str(extra_data.get("manifest_sha256") or "")
    current_manifest_sha256 = str(next_config.get("manifest_sha256") or "")
    smoke_status = status
    if status == "success" and manifest_sha256 != current_manifest_sha256:
        smoke_status = "stale"

    smoke_summary: dict[str, Any] = {
        "status": smoke_status,
        "task_id": task_id,
        "manifest_sha256": manifest_sha256,
        "example_name": extra_data.get("example_name"),
        "finished_at": finished_at.isoformat() if finished_at else None,
    }
    if error_message:
        smoke_summary["error"] = error_message
    if isinstance(output_result, dict) and output_result.get("remote_run_id"):
        smoke_summary["remote_run_id"] = output_result["remote_run_id"]

    auto_publish = smoke_status == "success" and bool(
        extra_data.get("publish_on_success")
        or next_config.get("pending_publish_on_smoke_success")
    )
    if auto_publish:
        next_config.pop("pending_publish_on_smoke_success", None)
        smoke_summary["auto_published"] = True

    next_config["last_smoke_test"] = smoke_summary
    return RemoteToolSmokeResultUpdate(config=next_config, auto_publish=auto_publish)


def remote_manifest_sha256(manifest_payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        manifest_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def remote_tool_config(
    *,
    base_url: str,
    manifest_payload: dict[str, Any],
    manifest_sha256: str,
    discovery: RemoteToolDiscoveryResult,
    publish_on_success: bool,
) -> dict[str, Any]:
    parameters_schema = dict(manifest_payload.get("parameters_schema") or {})
    config = {
        "type": "remote_api",
        "mode": "remote_tool_v1",
        "base_url": base_url.rstrip("/"),
        "tool_slug": manifest_payload.get("metadata", {}).get("slug"),
        "manifest": manifest_payload,
        "manifest_sha256": manifest_sha256,
        "endpoints": dict(manifest_payload.get("endpoints") or {}),
        "artifacts": dict(manifest_payload.get("artifacts") or {}),
        "parameters_schema": parameters_schema,
        "capabilities": dict(manifest_payload.get("capabilities") or {}),
        "input_schema": parameters_schema,
        "output_schema": {
            "type": "object",
            "properties": {
                "result_version": {"type": "string"},
                "artifacts": {"type": "object"},
                "relations": {"type": "array"},
            },
        },
        "remote_health": discovery.health,
        "remote_examples": (
            discovery.examples.model_dump(mode="json") if discovery.examples else None
        ),
        "registration_diagnostics": [
            stage.model_dump() for stage in discovery.stages
        ],
    }
    if publish_on_success:
        config["pending_publish_on_smoke_success"] = True
    return config
