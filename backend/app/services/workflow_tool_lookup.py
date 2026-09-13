"""Workflow tool availability lookup."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import ValidationException
from app.models.tools import Tool, ToolProviderType, ToolStatus


async def load_available_workflow_tool(
    db: AsyncSession,
    *,
    node: dict[str, Any],
) -> Tool:
    """Load the active tool version a workflow node is allowed to run."""
    tool_id = node.get("tool_id")
    tool_slug = node.get("tool_slug")
    query = select(Tool).options(selectinload(Tool.current_version))
    if tool_id:
        query = query.where(Tool.id == str(tool_id))
    elif tool_slug:
        query = query.where(Tool.slug == str(tool_slug))
    else:
        raise ValidationException("Workflow tool node is missing tool_id or tool_slug")

    result = await db.execute(query)
    tool = result.scalar_one_or_none()
    if not tool:
        raise ValidationException(f"Workflow tool is not configured: {tool_slug or tool_id}")
    if tool.status != ToolStatus.PUBLISHED.value or (
        tool.is_public is not True and not _is_private_platform_builtin(tool)
    ):
        raise ValidationException(f"Workflow tool is unavailable: {tool.slug}")
    if (
        not tool.current_version
        or tool.current_version.is_active is not True
        or tool.current_version.deprecated is True
    ):
        raise ValidationException(f"Workflow tool has no active version: {tool.slug}")
    return tool


def _is_private_platform_builtin(tool: Tool) -> bool:
    current_version = tool.current_version
    config = current_version.config if current_version and current_version.config else {}
    return (
        tool.provider_type == ToolProviderType.PLATFORM.value
        and isinstance(config, dict)
        and config.get("type") == "builtin"
    )
