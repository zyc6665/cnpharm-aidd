"""Dynamic AIDD agent capability registry.

Resolution order (per tool):
1. DB ``tool_capabilities`` table (explicit registration)
2. Tool version config ``agent_capability`` (dynamic discovery)
3. Static ``AIDD_TOOL_CAPABILITIES`` dict (legacy fallback)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.tools.capabilities import (
    AIDD_TOOL_CAPABILITIES,
    CapabilityInput,
    CapabilityOutput,
    OutputMatch,
    ToolCapability,
)
from app.common.exceptions import ValidationException
from app.models.tool_capabilities import ToolCapability as ToolCapabilityModel
from app.models.tools import Tool, ToolStatus
from app.services.tool_contracts import (
    build_tool_contract,
    build_virtual_tool_contract,
    tool_contract_to_agent_summary,
)
from app.services.semantic_types import normalize_semantic_type
from app.tool_packages.config_resolver import tool_package_v2_manifest


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


def _db_row_to_capability(row: ToolCapabilityModel) -> ToolCapability:
    """Convert a DB row to the domain dataclass."""
    return ToolCapability(
        tool_slug=row.capability,  # capability 字段存储工具 slug
        capability=row.capability,
        stage=row.stage,
        inputs=tuple(
            CapabilityInput(
                normalize_semantic_type(str(item["semantic_type"])),
                str(item.get("field") or normalize_semantic_type(str(item["semantic_type"]))),
                required=bool(item.get("required", True)),
                accepted_extensions=_as_tuple(item.get("accepted_extensions")),
            )
            for item in (row.inputs or [])
        ),
        outputs=tuple(
            CapabilityOutput(
                normalize_semantic_type(str(item["semantic_type"])),
                str(item.get("source") or "output_files"),
                match=_parse_output_match(item.get("match")),
                path=str(item["path"]) if item.get("path") else None,
                required=bool(item.get("required", True)),
            )
            for item in (row.outputs or [])
        ),
        defaults=dict(row.defaults or {}),
        virtual=False,
    )


# ---------------------------------------------------------------------------
# Config-based discovery (existing mechanism, kept as fallback)
# ---------------------------------------------------------------------------


def capability_from_config(tool_slug: str, config: dict[str, Any]) -> ToolCapability | None:
    """Build a ToolCapability from tool version config, if agent metadata is enabled."""
    raw_capability = config.get(AGENT_CAPABILITY_CONFIG_KEY)
    if not isinstance(raw_capability, dict) or raw_capability.get("enabled") is not True:
        return None

    inputs = tuple(
        CapabilityInput(
            normalize_semantic_type(str(item["semantic_type"])),
            str(item.get("field") or normalize_semantic_type(str(item["semantic_type"]))),
            required=bool(item.get("required", True)),
            accepted_extensions=_as_tuple(item.get("accepted_extensions")),
        )
        for item in raw_capability.get("inputs", [])
        if isinstance(item, dict) and item.get("semantic_type")
    )
    outputs = tuple(
        CapabilityOutput(
            normalize_semantic_type(str(item["semantic_type"])),
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


def capability_from_tool_package_config(tool_slug: str, config: dict[str, Any]) -> ToolCapability | None:
    """Build a ToolCapability from a Tool Package v2 standard Artifact contract."""
    manifest = tool_package_v2_manifest(config)
    if manifest is None or manifest.exposure.agent is not True:
        return None

    inputs = tuple(
        CapabilityInput(
            item.type,
            item.name,
            required=item.required,
        )
        for item in manifest.artifacts.inputs
    )
    outputs = tuple(
        CapabilityOutput(
            item.type,
            "artifact",
            match=OutputMatch(content_type=item.type),
            path=item.name,
            required=item.required,
        )
        for item in manifest.artifacts.outputs
    )
    if not inputs or not outputs:
        return None

    return ToolCapability(
        tool_slug=tool_slug,
        capability=manifest.metadata.slug,
        stage=manifest.metadata.slug,
        inputs=inputs,
        outputs=outputs,
        defaults={},
        virtual=False,
    )


def capability_from_tool(tool: Tool) -> ToolCapability | None:
    """Resolve a platform tool capability from current version config or legacy static registry."""
    config = tool.current_version.config if tool.current_version is not None else {}
    package_capability = capability_from_tool_package_config(tool.slug, config or {})
    if package_capability is not None:
        return package_capability

    dynamic_capability = capability_from_config(tool.slug, config or {})
    if dynamic_capability is not None:
        return dynamic_capability

    static_capability = AIDD_TOOL_CAPABILITIES.get(tool.slug)
    if static_capability and not static_capability.virtual:
        return static_capability
    return None


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------


def capability_to_tool_summary(capability: ToolCapability) -> dict[str, Any]:
    return tool_contract_to_agent_summary(build_virtual_tool_contract(capability))


def builtin_tool_summaries() -> list[dict[str, Any]]:
    return [
        capability_to_tool_summary(capability)
        for capability in AIDD_TOOL_CAPABILITIES.values()
        if capability.virtual
    ]


# ---------------------------------------------------------------------------
# Tool availability check
# ---------------------------------------------------------------------------


def _tool_is_agent_available(tool: Tool) -> bool:
    current_version = tool.current_version
    return (
        tool.status == ToolStatus.PUBLISHED.value
        and tool.is_public is True
        and current_version is not None
        and current_version.is_active is True
        and current_version.deprecated is not True
    )

# ---------------------------------------------------------------------------
# DB-first capability loading (primary path)
# ---------------------------------------------------------------------------


async def _load_db_capabilities(db: AsyncSession) -> dict[str, ToolCapability]:
    """Load capabilities from the DB table, keyed by tool_id (or slug for builtins)."""
    result = await db.execute(
        select(ToolCapabilityModel).where(
            ToolCapabilityModel.is_enabled.is_(True),
            ToolCapabilityModel.is_builtin.is_(False),
        )
    )
    db_caps: dict[str, ToolCapability] = {}
    for row in result.scalars().all():
        if not row.inputs or not row.outputs:
            continue
        capability = _db_row_to_capability(row)
        db_caps[row.tool_id] = capability
    return db_caps


async def load_available_tool_capabilities(db: AsyncSession) -> list[ToolCapability]:
    """Return all capabilities available to the AIDD agent.

    Priority: DB table → config-based → static registry.
    Virtual (built-in) tools are always included from the static registry.
    """
    # 1. Load DB-registered capabilities
    db_caps = await _load_db_capabilities(db)

    capabilities: list[ToolCapability] = []

    result = await db.execute(
        select(Tool)
        .options(selectinload(Tool.current_version))
        .where(Tool.status == ToolStatus.PUBLISHED.value, Tool.is_public.is_(True))
    )
    for tool in result.scalars().all():
        if not _tool_is_agent_available(tool):
            continue
        package_capability = capability_from_tool_package_config(
            tool.slug,
            tool.current_version.config if tool.current_version is not None else {},
        )
        capability = package_capability or db_caps.get(tool.id) or capability_from_tool(tool)
        if capability is None:
            continue
        capabilities.append(
            ToolCapability(
                tool_slug=tool.slug,
                capability=capability.capability,
                stage=capability.stage,
                inputs=capability.inputs,
                outputs=capability.outputs,
                defaults=capability.defaults,
                virtual=False,
            )
        )

    # 4. Always include virtual (built-in) tools from static registry
    capabilities.extend(
        capability
        for capability in AIDD_TOOL_CAPABILITIES.values()
        if capability.virtual
    )
    return capabilities


async def load_available_tool_summaries(db: AsyncSession) -> list[dict[str, Any]]:
    """Return agent-consumable tool summaries for all available capabilities."""
    caps = await load_available_tool_capabilities(db)
    summaries: list[dict[str, Any]] = []
    for cap in caps:
        if cap.virtual:
            summaries.append(capability_to_tool_summary(cap))
        else:
            # For real tools, build from the tool record
            result = await db.execute(
                select(Tool)
                .options(selectinload(Tool.current_version))
                .where(Tool.slug == cap.tool_slug)
            )
            tool = result.scalar_one_or_none()
            if tool and _tool_is_agent_available(tool):
                summaries.append(
                    tool_contract_to_agent_summary(
                        build_tool_contract(tool, capability=cap)
                    )
                )
    return summaries


async def load_tool_capability(db: AsyncSession, tool_slug: str) -> ToolCapability:
    """Load a single tool's capability by slug.

    Resolution order: DB table → config-based → static registry.
    """
    # 1. Static virtual tools
    static_capability = AIDD_TOOL_CAPABILITIES.get(tool_slug)
    if static_capability and static_capability.virtual:
        return static_capability

    # 2. Check DB table (parenthesised import to avoid Base.metadata registration races)
    from app.models.tool_capabilities import ToolCapability as TCM

    tool_result = await db.execute(
        select(Tool)
        .options(selectinload(Tool.current_version))
        .where(Tool.slug == tool_slug)
    )
    tool = tool_result.scalar_one_or_none()

    if tool:
        if not _tool_is_agent_available(tool):
            raise ValidationException(f"智能体工具不可用: {tool_slug}")

        package_capability = capability_from_tool_package_config(
            tool.slug,
            tool.current_version.config if tool.current_version is not None else {},
        )
        if package_capability is not None:
            return package_capability

        db_result = await db.execute(
            select(TCM).where(
                TCM.tool_id == tool.id,
                TCM.is_enabled.is_(True),
            )
        )
        db_row = db_result.scalar_one_or_none()
        if db_row and db_row.inputs and db_row.outputs:
            cap = _db_row_to_capability(db_row)
            return ToolCapability(
                tool_slug=tool_slug,
                capability=cap.capability,
                stage=cap.stage,
                inputs=cap.inputs,
                outputs=cap.outputs,
                defaults=cap.defaults,
                virtual=False,
            )

    # 3. Fallback: config-based + static registry
    if not tool:
        raise ValidationException(f"智能体工具未配置: {tool_slug}")

    capability = capability_from_tool(tool)
    if capability is None:
        raise ValidationException(f"智能体工具缺少 agent_capability 配置: {tool_slug}")
    return capability


# ---------------------------------------------------------------------------
# Capability registration helper (for tool import pipeline)
# ---------------------------------------------------------------------------


async def upsert_capability_from_config(
    db: AsyncSession,
    tool: Tool,
) -> ToolCapabilityModel | None:
    """Insert or update a DB capability row from the tool's current version config.

    Returns the model row if ``agent_capability`` is present and enabled, else None.
    """
    # Re-query with eager-load to avoid MissingGreenlet on lazy relationships
    reload_result = await db.execute(
        select(Tool)
        .options(selectinload(Tool.current_version))
        .where(Tool.id == tool.id)
    )
    fresh_tool = reload_result.scalar_one()

    result = await db.execute(
        select(ToolCapabilityModel).where(ToolCapabilityModel.tool_id == fresh_tool.id)
    )
    row = result.scalar_one_or_none()

    config = fresh_tool.current_version.config if fresh_tool.current_version is not None else {}
    raw = config.get(AGENT_CAPABILITY_CONFIG_KEY)
    if not isinstance(raw, dict) or raw.get("enabled") is not True:
        if row is not None and row.is_enabled:
            row.is_enabled = False
            await db.flush()
        return None

    if row is None:
        row = ToolCapabilityModel(tool_id=fresh_tool.id)
        db.add(row)

    row.capability = str(raw.get("capability") or fresh_tool.slug)
    row.stage = str(raw.get("stage") or raw.get("capability") or "general")
    row.inputs = raw.get("inputs", [])
    row.outputs = raw.get("outputs", [])
    row.defaults = raw.get("defaults", {})
    row.is_builtin = False
    row.is_enabled = True

    await db.flush()
    return row
