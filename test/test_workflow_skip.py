"""Workflow skip propagation tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.workflow_skip import mark_unreachable_nodes_skipped  # noqa: E402


def test_mark_unreachable_nodes_skipped_cascades_through_dead_branch() -> None:
    definition = {
        "edges": [
            {"source": "inactive", "target": "child"},
            {"source": "child", "target": "grandchild"},
        ]
    }
    node_states = {
        "inactive": {"status": "pending"},
        "child": {"status": "pending"},
        "grandchild": {"status": "pending"},
    }

    mark_unreachable_nodes_skipped(
        node_states,
        "inactive",
        "Branch not active",
        definition=definition,
    )

    assert node_states["inactive"]["status"] == "skipped"
    assert node_states["child"]["status"] == "skipped"
    assert node_states["grandchild"]["status"] == "skipped"


def test_mark_unreachable_nodes_skipped_preserves_reachable_merge_node() -> None:
    definition = {
        "edges": [
            {"source": "inactive", "target": "merge"},
            {"source": "active", "target": "merge"},
            {"source": "merge", "target": "downstream"},
        ]
    }
    node_states = {
        "inactive": {"status": "pending"},
        "active": {"status": "pending"},
        "merge": {"status": "pending"},
        "downstream": {"status": "pending"},
    }

    mark_unreachable_nodes_skipped(
        node_states,
        "inactive",
        "Branch not active",
        definition=definition,
    )

    assert node_states["inactive"]["status"] == "skipped"
    assert node_states["merge"]["status"] == "pending"
    assert node_states["downstream"]["status"] == "pending"
