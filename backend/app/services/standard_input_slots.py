"""Shared helpers for standard Artifact input slots."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Iterable

from app.services.tool_contracts import build_tool_contract
from app.tool_packages.config_resolver import tool_package_v2_manifest_data


def artifact_input_slots_from_contract(
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    artifacts = (
        contract.get("artifacts")
        if isinstance(contract.get("artifacts"), dict)
        else {}
    )
    inputs = artifacts.get("inputs") if isinstance(artifacts, dict) else []
    return [dict(slot) for slot in inputs or [] if isinstance(slot, dict)]


def artifact_input_slots_for_run(
    contract: dict[str, Any],
    workflow_node: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    slots_by_name = artifact_input_slots_by_name(
        artifact_input_slots_from_contract(contract)
    )
    if isinstance(workflow_node, dict):
        for slot in workflow_node.get("artifact_input_slots") or []:
            if isinstance(slot, dict) and str(slot.get("name") or ""):
                slots_by_name[str(slot["name"])] = dict(slot)
    return list(slots_by_name.values())


def artifact_input_slots_by_name(
    slots: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        str(slot.get("name")): dict(slot)
        for slot in slots
        if isinstance(slot, dict) and str(slot.get("name") or "")
    }


def artifact_input_slots_by_name_for_node(
    node: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    slots = node.get("artifact_input_slots") if isinstance(node, dict) else []
    return artifact_input_slots_by_name(
        slot for slot in slots or [] if isinstance(slot, dict)
    )


def artifact_input_slots_by_name_for_tool(
    tool: Any,
    tool_version: Any,
) -> dict[str, dict[str, Any]]:
    contract = build_tool_contract(
        SimpleNamespace(
            id=getattr(tool, "id", None),
            slug=getattr(tool, "slug", None),
            name=getattr(tool, "name", None),
            description=getattr(tool, "description", None),
            status=getattr(tool, "status", None),
            is_public=getattr(tool, "is_public", None),
            timeout_sec=getattr(tool, "timeout_sec", None),
            current_version=tool_version,
        )
    )
    return artifact_input_slots_by_name(
        artifact_input_slots_from_contract(contract)
    )


def tool_accepts_materialized_standard_uploads(config: object) -> bool:
    return tool_package_v2_manifest_data(config) is not None


def tool_accepts_standard_input_bindings(config: dict[str, Any]) -> bool:
    return tool_accepts_materialized_standard_uploads(config)
