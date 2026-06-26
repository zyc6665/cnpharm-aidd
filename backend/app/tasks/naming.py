"""Task naming and output extraction helpers shared across API, service and worker layers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


def _sanitize_task_name(name: Optional[str]) -> Optional[str]:
    if name is None:
        return None

    normalized = name.strip()
    return normalized or None


def _build_default_task_name(
    *,
    tool_name: Optional[str],
    created_at: Optional[datetime],
    task_id: Optional[str],
) -> str:
    if tool_name and created_at:
        return f"{tool_name} {created_at.strftime('%Y-%m-%d %H:%M')}"

    if tool_name:
        return tool_name

    if task_id:
        return f"Task {str(task_id)[:8]}"

    return "Task"


def resolve_task_display_name(
    *,
    name: Optional[str],
    tool_name: Optional[str],
    created_at: Optional[datetime],
    task_id: Optional[str],
) -> str:
    return _sanitize_task_name(name) or _build_default_task_name(
        tool_name=tool_name,
        created_at=created_at,
        task_id=task_id,
    )


def _dedupe_file_ids(file_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for file_id in file_ids:
        if not file_id or file_id in seen:
            continue
        seen.add(file_id)
        ordered.append(file_id)
    return ordered


def _extract_file_ids_from_result(
    result: Any,
    *,
    dedupe: bool = False,
    skip_empty: bool = False,
) -> list[str]:
    """Extract output file ids from a task result dict.

    Supports both the top-level ``output_file_ids`` key and the nested
    ``result.output_file_ids`` shape produced by some executors.
    """
    if not isinstance(result, dict):
        return []

    file_ids: list[str] = []

    direct_file_ids = result.get("output_file_ids")
    if isinstance(direct_file_ids, list):
        file_ids.extend(str(file_id) for file_id in direct_file_ids if not skip_empty or file_id)

    nested_result = result.get("result")
    if isinstance(nested_result, dict):
        nested_file_ids = nested_result.get("output_file_ids")
        if isinstance(nested_file_ids, list):
            file_ids.extend(
                str(file_id) for file_id in nested_file_ids if not skip_empty or file_id
            )

    if dedupe:
        return _dedupe_file_ids(file_ids)

    return file_ids
