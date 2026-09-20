"""Canonical mapping between persisted tool and execution executor types."""

from __future__ import annotations


TOOL_TYPE_TO_EXECUTION_TYPES: dict[str, tuple[str, ...]] = {
    "docker_image": ("container",),
    "python_script": ("cli",),
    "ssh_job": ("remote_job",),
    "remote_api": ("remote_job",),
}


def execution_types_for_tool_type(tool_type: str) -> tuple[str, ...] | None:
    """Return execution contract types supported by a persisted tool type."""
    return TOOL_TYPE_TO_EXECUTION_TYPES.get(str(tool_type or "").strip())


def execution_type_for_tool_type(tool_type: str) -> str:
    """Return the single execution type for a tool or raise a clear error."""
    normalized = str(tool_type or "").strip()
    supported = execution_types_for_tool_type(normalized)
    if supported is None:
        if normalized == "builtin":
            raise ValueError("builtin tools do not use the external execution contract")
        raise ValueError(f"unsupported tool executor type: {normalized or '<missing>'}")
    if len(supported) != 1:
        raise ValueError(f"tool executor type has no unique mapping: {normalized}")
    return supported[0]
