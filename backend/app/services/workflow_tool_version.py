"""Resolve the tool version a workflow node should execute with.

建 run 时会把 ``tool_version`` 快照写进 run 定义/节点状态。节点后续调度必须
沿用这个快照，否则工具发新版本后，一次 run 内就会出现前后节点混用两个版本的
情况——产物契约可能不兼容，追溯也无法解释。只有确实没有快照时才回退到实时的
``Tool.current_version_id``。
"""

from __future__ import annotations

from typing import Any


def resolve_tool_version(
    state: dict[str, Any] | None,
    node: dict[str, Any] | None,
    tool: Any,
) -> tuple[Any, Any]:
    """Return ``(tool_version_id, tool_version_label)`` for a workflow node.

    优先取 run/节点状态里的 ``tool_version`` 快照，其次取显式的
    ``tool_version_id``，两者都没有时回退到工具的实时当前版本。
    """
    state = state or {}
    node = node or {}
    snapshot = state.get("tool_version") or node.get("tool_version") or {}
    version_id = (
        snapshot.get("id")
        or state.get("tool_version_id")
        or node.get("tool_version_id")
    )
    if version_id:
        return version_id, snapshot.get("version")
    current_version = getattr(tool, "current_version", None)
    return (
        getattr(tool, "current_version_id", None),
        getattr(current_version, "version", None),
    )
