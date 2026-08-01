"""Placeholder raw model entrypoint used by the model package template."""

from __future__ import annotations

import csv
from pathlib import Path


def predict(input_csv: Path, output_dir: Path) -> Path:
    """Read a molecule table and emit a deterministic placeholder prediction table."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_csv = output_dir / "predictions.csv"
    with input_csv.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = reader.fieldnames or []
        molecule_id_field = "molecule_id" if "molecule_id" in fieldnames else fieldnames[0]
        rows = list(reader)
    with output_csv.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=[molecule_id_field, "score"])
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            writer.writerow({molecule_id_field: row[molecule_id_field], "score": round(index / 10, 3)})
    return output_csv
