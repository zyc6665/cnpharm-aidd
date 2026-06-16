"""Dynamic AIDD agent capability registry."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.aidd.capabilities import (
    AIDD_TOOL_CAPABILITIES,
    CapabilityInput,
    CapabilityOutput,
    OutputMatch,
    ToolCapability,
)
from app.common.exceptions import ValidationException
from app.models.tools import Tool, ToolStatus


AGENT_CAPABILITY_CONFIG_KEY = "agent_capability"


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value if item is not None)
    return ()


def _parse_output_match(data: Any) -> OutputMatch | None:
    if not isinstance(data, dict):
        return None
    return OutputMatch(
        extension=str(data["extension"]) if data.get("extension") else None,
        filename_contains_any=_as_tuple(data.get("filename_contains_any")),
        content_type=str(data["content_type"]) if data.get("content_type") else None,
    )


def capability_from_config(tool_slug: str, config: dict[str, Any]) -> ToolCapability | None:
    """Build a ToolCapability from tool version config, if agent metadata is enabled."""
    raw_capability = config.get(AGENT_CAPABILITY_CONFIG_KEY)
    if not isinstance(raw_capability, dict) or raw_capability.get("enabled") is not True:
        return None

    inputs = tuple(
        CapabilityInput(
            str(item["semantic_type"]),
            str(item.get("field") or item["semantic_type"]),
            required=bool(item.get("required", True)),
            accepted_extensions=_as_tuple(item.get("accepted_extensions")),
        )
        for item in raw_capability.get("inputs", [])
        if isinstance(item, dict) and item.get("semantic_type")
    )
    outputs = tuple(
        CapabilityOutput(
            str(item["semantic_type"]),
            str(item.get("source") or "output_files"),
            match=_parse_output_match(item.get("match")),
            path=str(item["path"]) if item.get("path") else None,
            required=bool(item.get("required", True)),
        )
        for item in raw_capability.get("outputs", [])
        if isinstance(item, dict) and item.get("semantic_type")
    )
    if not inputs:
        raise ValidationException(f"工具 {tool_slug} 的 agent_capability 缺少 inputs")
    if not outputs:
        raise ValidationException(f"工具 {tool_slug} 的 agent_capability 缺少 outputs")

    return ToolCapability(
        tool_slug=tool_slug,
        capability=str(raw_capability.get("capability") or "general_tool"),
        stage=str(raw_capability.get("stage") or raw_capability.get("capability") or "general"),
        inputs=inputs,
        outputs=outputs,
        defaults=dict(raw_capability.get("defaults") or {}),
        virtual=False,
    )


def capability_from_tool(tool: Tool) -> ToolCapability | None:
    """Resolve a platform tool capability from current version config or legacy static registry."""
    config = tool.current_version.config if tool.current_version is not None else {}
    dynamic_capability = capability_from_config(tool.slug, config or {})
    if dynamic_capability is not None:
        return dynamic_capability

    static_capability = AIDD_TOOL_CAPABILITIES.get(tool.slug)
    if static_capability and not static_capability.virtual:
        return static_capability
    return None


def capability_to_tool_summary(capability: ToolCapability) -> dict[str, Any]:
    return {
        "tool_slug": capability.tool_slug,
        "capability": capability.capability,
        "stage": capability.stage,
        "inputs": [item.semantic_type for item in capability.inputs],
        "outputs": [item.semantic_type for item in capability.outputs],
        "defaults": dict(capability.defaults),
        "virtual": capability.virtual,
    }


def builtin_tool_summaries() -> list[dict[str, Any]]:
    return [
        capability_to_tool_summary(capability)
        for capability in AIDD_TOOL_CAPABILITIES.values()
        if capability.virtual
    ]


def _tool_is_agent_available(tool: Tool) -> bool:
    current_version = tool.current_version
    return (
        tool.status == ToolStatus.PUBLISHED.value
        and tool.is_public is True
        and current_version is not None
        and current_version.is_active is True
        and current_version.deprecated is not True
    )


async def load_available_tool_capabilities(db: AsyncSession) -> list[ToolCapability]:
    result = await db.execute(
        select(Tool)
        .options(selectinload(Tool.current_version))
        .where(Tool.status == ToolStatus.PUBLISHED.value, Tool.is_public.is_(True))
    )
    capabilities: list[ToolCapability] = []
    for tool in result.scalars().all():
        if not _tool_is_agent_available(tool):
            continue
        capability = capability_from_tool(tool)
        if capability is not None:
            capabilities.append(capability)

    capabilities.extend(
        capability
        for capability in AIDD_TOOL_CAPABILITIES.values()
        if capability.virtual
    )
    return capabilities


async def load_available_tool_summaries(db: AsyncSession) -> list[dict[str, Any]]:
    return [
        capability_to_tool_summary(capability)
        for capability in await load_available_tool_capabilities(db)
    ]


async def load_tool_capability(db: AsyncSession, tool_slug: str) -> ToolCapability:
    static_capability = AIDD_TOOL_CAPABILITIES.get(tool_slug)
    if static_capability and static_capability.virtual:
        return static_capability

    result = await db.execute(
        select(Tool)
        .options(selectinload(Tool.current_version))
        .where(Tool.slug == tool_slug)
    )
    tool = result.scalar_one_or_none()
    if not tool:
        raise ValidationException(f"智能体工具未配置: {tool_slug}")
    if not _tool_is_agent_available(tool):
        raise ValidationException(f"智能体工具不可用: {tool_slug}")

    capability = capability_from_tool(tool)
    if capability is None:
        raise ValidationException(f"智能体工具缺少 agent_capability 配置: {tool_slug}")
    return capability
