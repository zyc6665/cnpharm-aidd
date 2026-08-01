"""Runtime data contracts for the MolP-PC model package."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TableSummary:
    path: Path
    molecule_id_field: str
    row_count: int
    columns: list[str]
    property_columns: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RunRequest:
    task_id: str
    tool_slug: str
    tool_version: str
    input_csv: Path
    device: str
    parameters: dict[str, Any] = field(default_factory=dict)
