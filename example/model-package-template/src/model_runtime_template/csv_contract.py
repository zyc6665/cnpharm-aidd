"""CSV contract checks for the template input and output tables."""

from __future__ import annotations

import csv
from pathlib import Path

from .contracts import TableSummary


DEFAULT_MOLECULE_ID_FIELD = "molecule_id"


def inspect_molecule_table(
    path: Path,
    *,
    molecule_id_field: str = DEFAULT_MOLECULE_ID_FIELD,
) -> TableSummary:
    rows, fieldnames = _read_csv(path)
    if molecule_id_field not in fieldnames:
        raise ValueError(f"Input table must contain {molecule_id_field} column: {path}")
    return TableSummary(
        path=path,
        molecule_id_field=molecule_id_field,
        row_count=len(rows),
        columns=fieldnames,
    )


def inspect_prediction_table(
    path: Path,
    *,
    molecule_id_field: str = DEFAULT_MOLECULE_ID_FIELD,
) -> TableSummary:
    rows, fieldnames = _read_csv(path)
    if molecule_id_field not in fieldnames:
        raise ValueError(f"Prediction table must contain {molecule_id_field} column: {path}")
    property_columns = [column for column in fieldnames if column != molecule_id_field]
    if not property_columns:
        raise ValueError(f"Prediction table must contain property columns: {path}")
    return TableSummary(
        path=path,
        molecule_id_field=molecule_id_field,
        row_count=len(rows),
        columns=fieldnames,
        property_columns=property_columns,
    )


def _read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV file does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if not fieldnames:
        raise ValueError(f"CSV file has no header: {path}")
    return rows, fieldnames
