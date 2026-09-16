"""Remote tool registration config and publish rules."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.remote_tools.client import RemoteToolDiscoveryResult


REMOTE_TOOL_SMOKE_REQUIRED_ERROR = "remote_tool_v1 requires successful smoke test before publish"
REMOTE_TOOL_SMOKE_HASH_MISMATCH_ERROR = (
    "remote_tool_v1 smoke test manifest hash does not match current manifest"
)


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
