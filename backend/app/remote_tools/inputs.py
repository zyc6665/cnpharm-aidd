"""Remote tool input protocol helpers."""

from __future__ import annotations

from typing import Any


def remote_example_input_refs(extra_data: Any) -> dict[str, Any]:
    data = extra_data if isinstance(extra_data, dict) else {}
    inputs = data.get("remote_example_inputs")
    return dict(inputs) if isinstance(inputs, dict) else {}


def standard_input_bindings(extra_data: Any) -> dict[str, str]:
    data = extra_data if isinstance(extra_data, dict) else {}
    bindings = data.get("input_bindings")
    if not isinstance(bindings, dict):
        return {}
    return {
        str(input_name): str(version_id)
        for input_name, version_id in bindings.items()
        if str(input_name).strip() and str(version_id).strip()
    }


def remote_artifact_input_declarations(config: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = config.get("artifacts") if isinstance(config, dict) else None
    raw_inputs = artifacts.get("inputs") if isinstance(artifacts, dict) else None
    if not isinstance(raw_inputs, list):
        return []
    return [item for item in raw_inputs if isinstance(item, dict)]
