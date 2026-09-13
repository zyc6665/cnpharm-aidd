"""Workflow node skip propagation helpers."""

from __future__ import annotations

from typing import Any

from app.common.time import utcnow_iso
from app.services.workflow_validation import workflow_edges


_NON_SKIPPABLE_STATUSES = {"success", "failure", "skipped", "waiting_task", "running"}


def mark_unreachable_nodes_skipped(
    node_states: dict[str, Any],
    node_id: str,
    reason: str,
    *,
    definition: dict[str, Any] | None = None,
    force: bool = True,
    visited: set[str] | None = None,
) -> None:
    """Mark a dead branch and descendants that have no remaining live upstream."""
    if visited is None:
        visited = set()
    if node_id in visited:
        return
    visited.add(node_id)

    state = dict(node_states.get(node_id) or {})
    if state.get("status") in _NON_SKIPPABLE_STATUSES:
        return
    if not force and definition is not None and not _all_upstream_nodes_skipped(
        node_states,
        definition=definition,
        node_id=node_id,
    ):
        return

    state.update({
        "status": "skipped",
        "skip_reason": reason,
        "finished_at": utcnow_iso(),
    })
    node_states[node_id] = state

    if definition is None:
        return
    for edge in workflow_edges(definition):
        if str(edge.get("source") or "") != node_id:
            continue
        target = str(edge.get("target") or "")
        if not target:
            continue
        mark_unreachable_nodes_skipped(
            node_states,
            target,
            reason,
            definition=definition,
            force=False,
            visited=visited,
        )


def _all_upstream_nodes_skipped(
    node_states: dict[str, Any],
    *,
    definition: dict[str, Any],
    node_id: str,
) -> bool:
    upstream_ids = [
        str(edge.get("source") or "")
        for edge in workflow_edges(definition)
        if str(edge.get("target") or "") == node_id
    ]
    return bool(upstream_ids) and all(
        (node_states.get(upstream_id) or {}).get("status") == "skipped"
        for upstream_id in upstream_ids
    )
