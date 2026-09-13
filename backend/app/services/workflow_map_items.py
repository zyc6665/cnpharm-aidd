"""Workflow map item resolution."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ValidationException
from app.models.files import File as FileModel
from app.models.workflows import WorkflowRun
from app.services.semantic_types import normalize_semantic_type


async def resolve_map_items(
    db: AsyncSession,
    *,
    over: str,
    run: WorkflowRun,
    node_states: dict[str, Any],
) -> list[Any]:
    """Resolve a map node ``over`` reference to iterable work items."""
    if over.startswith("workflow_input:"):
        key = over.split(":", 1)[1]
        raw = (run.input_files or {}).get(key)
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return list(raw.values())
        return [raw] if raw is not None else []

    if over.startswith("node:"):
        parts = over.split(":", 2)
        if len(parts) != 3:
            raise ValidationException(f"Invalid map over reference: {over}")
        source_node_id = parts[1]
        source_semantic_type = normalize_semantic_type(parts[2])
        source_state = node_states.get(source_node_id) or {}
        source_output = (source_state.get("semantic_outputs") or {}).get(source_semantic_type)
        if not source_output:
            return []

        value = source_output.get("value")
        if isinstance(value, list):
            return value

        file_id = source_output.get("file_id")
        if file_id:
            file_record = await db.get(FileModel, str(file_id))
            if file_record and file_record.storage_path:
                resolved = _read_map_items_from_file(Path(file_record.storage_path))
                if resolved is not None:
                    return resolved
        return [source_output]

    raise ValidationException(f"Unsupported map over reference: {over}")


def _read_map_items_from_file(path: Path) -> list[Any] | None:
    try:
        if path.suffix == ".csv":
            text = path.read_text(encoding="utf-8")
            return list(csv.DictReader(io.StringIO(text)))
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else [data]
    except (OSError, json.JSONDecodeError, csv.Error):
        return None
    return None
