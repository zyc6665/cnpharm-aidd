"""Workflow run definition materialization helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.standard_input_slots import tool_accepts_standard_input_bindings
from app.services.workflow_tool_lookup import load_available_workflow_tool
from app.services.workflow_validation import is_loop_node, is_tool_node, workflow_nodes


def _copy_node(node: dict[str, Any]) -> dict[str, Any]:
    """复制节点；loop 节点的 body 也复制，避免快照写回调用方原始定义。"""
    copied = dict(node)
    if is_loop_node(node):
        copied["body"] = [
            dict(body_node)
            for body_node in node.get("body") or []
            if isinstance(body_node, dict)
        ]
    return copied


def _tool_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """列出需要记录 tool_version 快照的节点，含 loop 节点的 body 子节点。"""
    tool_nodes: list[dict[str, Any]] = []
    for node in nodes:
        tool_nodes.append(node)
        if is_loop_node(node):
            tool_nodes.extend(
                body_node
                for body_node in node.get("body") or []
                if isinstance(body_node, dict)
            )
    return tool_nodes


async def materialize_workflow_run_definition(
    db: AsyncSession,
    *,
    definition: dict[str, Any],
) -> dict[str, Any]:
    materialized_definition = {
        **definition,
        "nodes": [_copy_node(node) for node in workflow_nodes(definition)],
        "edges": list(definition.get("edges") or []),
    }
    for node in _tool_nodes(materialized_definition["nodes"]):
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
