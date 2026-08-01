"""CSV contract checks for MolP-PC inputs and outputs."""

from __future__ import annotations

import csv
from pathlib import Path

from .contracts import TableSummary


MOLECULE_ID_FIELD = "SMILES"


def inspect_molecule_table(path: Path) -> TableSummary:
    """Validate a molecule table and return its summary."""
    rows, fieldnames = _read_csv(path)
    if MOLECULE_ID_FIELD not in fieldnames:
        raise ValueError(f"Input molecule table must contain {MOLECULE_ID_FIELD} column: {path}")
    return TableSummary(
        path=path,
        molecule_id_field=MOLECULE_ID_FIELD,
        row_count=len(rows),
        columns=fieldnames,
    )


def inspect_prediction_table(path: Path) -> TableSummary:
    """Validate a MolP-PC prediction table and return property columns."""
    rows, fieldnames = _read_csv(path)
    if MOLECULE_ID_FIELD not in fieldnames:
        raise ValueError(
            f"MolP-PC prediction table must contain {MOLECULE_ID_FIELD} column: {path}"
        )
    property_columns = [column for column in fieldnames if column != MOLECULE_ID_FIELD]
    if not property_columns:
        raise ValueError(f"MolP-PC prediction table must contain property columns: {path}")
    return TableSummary(
        path=path,
        molecule_id_field=MOLECULE_ID_FIELD,
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
