"""Workflow run definition materialization helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.standard_input_slots import tool_accepts_standard_input_bindings
from app.services.workflow_tool_lookup import load_available_workflow_tool
from app.services.workflow_validation import is_tool_node, workflow_nodes


async def materialize_workflow_run_definition(
    db: AsyncSession,
    *,
    definition: dict[str, Any],
) -> dict[str, Any]:
    materialized_definition = {
        **definition,
        "nodes": [dict(node) for node in workflow_nodes(definition)],
        "edges": list(definition.get("edges") or []),
    }
    for node in materialized_definition["nodes"]:
        if not is_tool_node(node):
            continue
        tool = await load_available_workflow_tool(db, node=node)
        node["tool_id"] = tool.id
        node["tool_slug"] = tool.slug
        node["tool_version"] = {
            "id": tool.current_version_id,
            "version": tool.current_version.version if tool.current_version else None,
        }
    return materialized_definition


async def workflow_requires_standard_binding_project(
    db: AsyncSession,
    definition: dict[str, Any],
) -> bool:
    for node in workflow_nodes(definition):
        if not is_tool_node(node):
            continue
        tool = await load_available_workflow_tool(db, node=node)
        config = getattr(getattr(tool, "current_version", None), "config", None)
        if tool_accepts_standard_input_bindings(config if isinstance(config, dict) else {}):
            return True
    return False
