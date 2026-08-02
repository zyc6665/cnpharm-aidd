"""Build standard platform results from MSIGN legacy outputs."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .io import file_ref, read_json, write_json


STANDARD_AFFINITY_FILENAME = "msign_affinity.csv"
AFFINITY_COLUMNS = [
    "complex_id",
    "predicted_affinity",
    "predicted_ligand_to_pocket",
    "predicted_pocket_to_ligand",
    "scale",
    "model_name",
    "distance_angstrom",
    "device",
]


def write_standard_result(
    *,
    request: dict[str, Any],
    raw_output_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Wrap a legacy MSIGN prediction envelope as molecule_table@1."""
    task = request.get("task") or {}
    parameters = request.get("parameters") or {}
    task_id = str(task.get("id") or request.get("task_id") or "unknown-task")
    tool_slug = str(task.get("tool_slug") or "msign-affinity-prediction")

    affinity_dir = output_dir / "artifacts" / "affinity"
    report_dir = output_dir / "reports"
    affinity_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    legacy_result = _load_legacy_result(raw_output_dir)
    outputs = legacy_result.get("outputs")
    if not isinstance(outputs, dict):
        outputs = legacy_result
    prediction = outputs.get("prediction")
    if not isinstance(prediction, dict):
        raise ValueError("MSIGN legacy output must contain outputs.prediction")

    row = _build_affinity_row(outputs=outputs, prediction=prediction, parameters=parameters)
    table_path = affinity_dir / STANDARD_AFFINITY_FILENAME
    _write_affinity_csv(table_path, row)

    metadata = {
        "molecule_id_field": "complex_id",
        "source_task_id": task_id,
        "source_input_refs": ["input:protein", "input:ligand"],
        "row_count": 1,
        "property_columns": [column for column in AFFINITY_COLUMNS if column != "complex_id"],
        "model_name": row["model_name"],
    }
    metadata_path = affinity_dir / "metadata.json"
    write_json(metadata_path, metadata)

    report = {
        "tool": tool_slug,
        "adapter": "msign_runtime",
        "status": "succeeded",
        "source_task_id": task_id,
        "complex_id": row["complex_id"],
        "model_name": row["model_name"],
        "distance_angstrom": row["distance_angstrom"],
    }
    report_path = report_dir / "report.json"
    write_json(report_path, report)

    result = {
        "result_version": "aidd.sciminer/result.v2",
        "artifacts": {
            "affinity": {
                "name": f"{task_id}_msign_affinity",
                "type": "molecule_table@1",
                "files": {
                    "table_file": file_ref(
                        output_dir=output_dir,
                        path=table_path,
                        content_type="text/csv",
                    ),
                    "metadata_json": file_ref(
                        output_dir=output_dir,
                        path=metadata_path,
                        content_type="application/json",
                    ),
                },
                "metadata": metadata,
            },
            "report": {
                "name": f"{task_id}_msign_adapter_report",
                "type": "run_report@1",
                "files": {
                    "report_json": file_ref(
                        output_dir=output_dir,
                        path=report_path,
                        content_type="application/json",
                    )
                },
                "metadata": {"source_task_id": task_id},
            },
        },
        "relations": [{"from": "report", "to": "affinity", "type": "describes"}],
    }
    write_json(output_dir / "result.json", result)
    return result


def _load_legacy_result(raw_output_dir: Path) -> dict[str, Any]:
    for candidate in (
        raw_output_dir / "result.json",
        raw_output_dir / "prediction.json",
        raw_output_dir / "artifacts" / "prediction.json",
    ):
        if candidate.is_file():
            return read_json(candidate)
    raise FileNotFoundError(f"Missing MSIGN legacy result in {raw_output_dir}")


def _build_affinity_row(
    *,
    outputs: dict[str, Any],
    prediction: dict[str, Any],
    parameters: dict[str, Any],
) -> dict[str, Any]:
    complex_id = outputs.get("complex_id") or parameters.get("complex_id") or "unknown-complex"
    return {
        "complex_id": str(complex_id),
        "predicted_affinity": prediction.get("predicted_affinity"),
        "predicted_ligand_to_pocket": prediction.get("predicted_ligand_to_pocket"),
        "predicted_pocket_to_ligand": prediction.get("predicted_pocket_to_ligand"),
        "scale": prediction.get("scale", ""),
        "model_name": outputs.get("model_name") or parameters.get("model_variant") or "",
        "distance_angstrom": outputs.get("distance_angstrom") or parameters.get("distance") or "",
        "device": outputs.get("device", ""),
    }


def _write_affinity_csv(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AFFINITY_COLUMNS)
        writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in AFFINITY_COLUMNS})
