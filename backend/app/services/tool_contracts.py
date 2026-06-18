"""Normalized tool contract serialization."""

from __future__ import annotations

from typing import Any

from app.services.semantic_types import normalize_semantic_type


TOOL_CONTRACT_VERSION = "1.0"


def build_tool_contract(tool: Any, *, capability: Any | None = None) -> dict[str, Any]:
    """Build the stable platform-facing contract for a persisted tool."""
    current_version = getattr(tool, "current_version", None)
    config = getattr(current_version, "config", None)
    if not isinstance(config, dict):
        config = {}

    return {
        "contract_version": TOOL_CONTRACT_VERSION,
        "id": getattr(tool, "id", None),
        "slug": getattr(tool, "slug", None),
        "name": getattr(tool, "name", None),
        "description": getattr(tool, "description", None),
        "status": getattr(tool, "status", None),
        "is_public": getattr(tool, "is_public", None),
        "version": _version_contract(current_version),
        "executor": _executor_contract(tool, config),
        "schema": {
            "input": _schema_object(config.get("input_schema")),
            "output": _schema_object(config.get("output_schema")),
        },
        "capability": _capability_contract(
            raw_capability=config.get("agent_capability"),
            capability=capability,
            virtual=False,
        ),
        "validation": {"status": "valid", "errors": []},
    }


def build_virtual_tool_contract(capability: Any) -> dict[str, Any]:
    """Build a contract for an Agent-only virtual tool."""
    slug = getattr(capability, "tool_slug", None)
    return {
        "contract_version": TOOL_CONTRACT_VERSION,
        "id": None,
        "slug": slug,
        "name": slug,
        "description": None,
        "status": "virtual",
        "is_public": True,
        "version": None,
        "executor": {"type": "builtin", "timeout_sec": None},
        "schema": {"input": {}, "output": {}},
        "capability": _capability_contract(
            raw_capability=None,
            capability=capability,
            virtual=True,
        ),
        "validation": {"status": "valid", "errors": []},
    }


def tool_contract_to_agent_summary(contract: dict[str, Any]) -> dict[str, Any]:
    """Convert a ToolContract into the current planner-facing Agent summary."""
    capability = contract.get("capability") if isinstance(contract.get("capability"), dict) else {}
    tool_version = contract.get("version") if isinstance(contract.get("version"), dict) else None
    slug = str(contract.get("slug") or "")
    return {
        "id": contract.get("id"),
        "slug": slug,
        "tool_slug": slug,
        "name": contract.get("name") or slug,
        "contract_version": contract.get("contract_version"),
        "tool_version": tool_version,
        "capability": capability.get("capability"),
        "stage": capability.get("stage"),
        "input_bindings": list(capability.get("inputs") or []),
        "output_rules": list(capability.get("outputs") or []),
        "inputs": [
            item.get("semantic_type")
            for item in capability.get("inputs", [])
            if isinstance(item, dict) and item.get("semantic_type")
        ],
        "outputs": [
            item.get("semantic_type")
            for item in capability.get("outputs", [])
            if isinstance(item, dict) and item.get("semantic_type")
        ],
        "defaults": dict(capability.get("defaults") or {}),
        "virtual": bool(capability.get("virtual")),
        "executor": contract.get("executor") or {},
        "validation": contract.get("validation") or {},
    }


def _version_contract(current_version: Any | None) -> dict[str, Any] | None:
    if current_version is None:
        return None
    return {
        "id": getattr(current_version, "id", None),
        "version": getattr(current_version, "version", None),
        "is_active": getattr(current_version, "is_active", None),
        "deprecated": getattr(current_version, "deprecated", None),
    }


def _executor_contract(tool: Any, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": str(config.get("type") or ""),
        "timeout_sec": config.get("timeout_sec", getattr(tool, "timeout_sec", None)),
    }


def _schema_object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _capability_contract(
    *,
    raw_capability: Any,
    capability: Any | None,
    virtual: bool,
) -> dict[str, Any]:
    if capability is not None:
        return _capability_object_contract(capability, virtual=virtual)

    if not isinstance(raw_capability, dict) or raw_capability.get("enabled") is not True:
        return {
            "enabled": False,
            "capability": None,
            "stage": None,
            "inputs": [],
            "outputs": [],
            "defaults": {},
            "virtual": virtual,
        }

    return {
        "enabled": True,
        "capability": raw_capability.get("capability"),
        "stage": raw_capability.get("stage"),
        "inputs": [
            _capability_input_contract(item)
            for item in raw_capability.get("inputs", [])
            if isinstance(item, dict) and item.get("semantic_type")
        ],
        "outputs": [
            _capability_output_contract(item)
            for item in raw_capability.get("outputs", [])
            if isinstance(item, dict) and item.get("semantic_type")
        ],
        "defaults": dict(raw_capability.get("defaults") or {}),
        "virtual": virtual,
    }


def _capability_object_contract(capability: Any, *, virtual: bool) -> dict[str, Any]:
    return {
        "enabled": True,
        "capability": getattr(capability, "capability", None),
        "stage": getattr(capability, "stage", None),
        "inputs": [
            {
                "semantic_type": _semantic_type(getattr(item, "semantic_type", None)),
                "field": getattr(item, "field", None),
                "required": getattr(item, "required", True),
                "accepted_extensions": list(getattr(item, "accepted_extensions", ()) or ()),
            }
            for item in getattr(capability, "inputs", ()) or ()
        ],
        "outputs": [
            {
                "semantic_type": _semantic_type(getattr(item, "semantic_type", None)),
                "source": getattr(item, "source", None),
                "match": _output_match_contract(getattr(item, "match", None)),
                "path": getattr(item, "path", None),
                "required": getattr(item, "required", True),
            }
            for item in getattr(capability, "outputs", ()) or ()
        ],
        "defaults": dict(getattr(capability, "defaults", {}) or {}),
        "virtual": virtual,
    }


def _capability_input_contract(item: dict[str, Any]) -> dict[str, Any]:
    semantic_type = _semantic_type(item.get("semantic_type"))
    return {
        "semantic_type": semantic_type,
        "field": item.get("field") or semantic_type,
        "required": bool(item.get("required", True)),
        "accepted_extensions": list(item.get("accepted_extensions") or []),
    }


def _capability_output_contract(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "semantic_type": _semantic_type(item.get("semantic_type")),
        "source": item.get("source") or "output_files",
        "match": _schema_object(item.get("match")),
        "path": item.get("path"),
        "required": bool(item.get("required", True)),
    }


def _output_match_contract(match: Any | None) -> dict[str, Any] | None:
    if match is None:
        return None
    return {
        "extension": getattr(match, "extension", None),
        "filename_contains_any": list(getattr(match, "filename_contains_any", ()) or ()),
        "content_type": getattr(match, "content_type", None),
    }


def _semantic_type(value: Any) -> str | None:
    if value is None:
        return None
    return normalize_semantic_type(str(value))
