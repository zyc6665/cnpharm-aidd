"""科研白板内容兼容读取工具。"""

from __future__ import annotations

from typing import Any


DEFAULT_VIEWPORT = {"x": 0, "y": 0, "zoom": 1}


def normalize_board_content(value: Any) -> dict[str, Any]:
    """将历史白板内容规范化为当前画布结构。"""

    if isinstance(value, dict):
        nodes = value.get("nodes")
        edges = value.get("edges")
        viewport = value.get("viewport")
    elif isinstance(value, list):
        nodes = value
        edges = []
        viewport = DEFAULT_VIEWPORT
    else:
        nodes = []
        edges = []
        viewport = DEFAULT_VIEWPORT

    return {
        "nodes": [node for node in nodes if isinstance(node, dict)]
        if isinstance(nodes, list)
        else [],
        "edges": [edge for edge in edges if isinstance(edge, dict)]
        if isinstance(edges, list)
        else [],
        "viewport": dict(viewport) if isinstance(viewport, dict) else dict(DEFAULT_VIEWPORT),
    }


def board_nodes(value: Any) -> list[dict[str, Any]]:
    return normalize_board_content(value)["nodes"]


def board_node_count(value: Any) -> int:
    return len(board_nodes(value))
