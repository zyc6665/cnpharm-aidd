from __future__ import annotations

from app.services.workflow_dependencies import (  # noqa: E402
    dependencies_satisfied,
    dependency_tool_node_ids,
)


def test_dependency_tool_node_ids_keeps_only_tool_dependencies() -> None:
    definition = {
        "nodes": [
            {"id": "fetch", "kind": "tool"},
            {"id": "branch", "kind": "condition", "expression": {"op": "==", "left": 1, "right": 1}},
            {"id": "score", "kind": "tool"},
        ],
        "edges": [
            {"source": "fetch", "target": "score"},
            {"source": "branch", "target": "score", "branch": "true"},
        ],
    }

    assert dependency_tool_node_ids(definition, "score") == {"fetch"}


def test_dependencies_satisfied_requires_tool_dependencies_and_active_branch() -> None:
    definition = {
        "nodes": [
            {"id": "fetch", "kind": "tool"},
            {"id": "branch", "kind": "condition", "expression": {"op": "==", "left": 1, "right": 1}},
            {"id": "score", "kind": "tool"},
        ],
        "edges": [
            {"source": "fetch", "target": "score"},
            {"source": "branch", "target": "score", "branch": "true"},
        ],
    }

    assert not dependencies_satisfied(
        definition=definition,
        node_states={
            "fetch": {"status": "running"},
            "branch": {"status": "success", "active_branch": "true"},
        },
        node_id="score",
    )
    assert not dependencies_satisfied(
        definition=definition,
        node_states={
            "fetch": {"status": "success"},
            "branch": {"status": "success", "active_branch": "false"},
        },
        node_id="score",
    )
    assert dependencies_satisfied(
        definition=definition,
        node_states={
            "fetch": {"status": "success"},
            "branch": {"status": "success", "active_branch": "true"},
        },
        node_id="score",
    )
