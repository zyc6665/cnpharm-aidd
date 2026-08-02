"""Build standard platform results from MolP-PC legacy outputs."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .csv_contract import inspect_prediction_table
from .io import file_ref, write_json


LEGACY_PREDICTION_FILENAME = "cb_data_result.csv"
LEGACY_PREDICTION_CANDIDATES = (
    LEGACY_PREDICTION_FILENAME,
    f"artifacts/{LEGACY_PREDICTION_FILENAME}",
)
STANDARD_PREDICTION_FILENAME = "molp_pc_predictions.csv"


def write_standard_result(
    *,
    request: dict[str, Any],
    raw_output_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Wrap a legacy MolP-PC prediction CSV as result.v2 and write output/result.json."""
    task = request.get("task") or {}
    task_id = str(task.get("id") or request.get("task_id") or "unknown-task")
    tool_slug = str(task.get("tool_slug") or request.get("task_name") or "molp-pc")

    properties_dir = output_dir / "artifacts" / "properties"
    report_dir = output_dir / "reports"
    properties_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    source_csv = _first_existing(raw_output_dir, LEGACY_PREDICTION_CANDIDATES)
    summary = inspect_prediction_table(source_csv)
    target_csv = properties_dir / STANDARD_PREDICTION_FILENAME
    shutil.copyfile(source_csv, target_csv)

    metadata = {
        "molecule_id_field": summary.molecule_id_field,
        "source_task_id": task_id,
        "source_input_ref": "input:molecules",
        "row_count": summary.row_count,
        "property_column_count": len(summary.property_columns),
        "property_columns": summary.property_columns,
        "model_name": "MolP-PC",
    }
    metadata_path = properties_dir / "metadata.json"
    write_json(metadata_path, metadata)

    report = {
        "tool": tool_slug,
        "adapter": "molp_pc_runtime",
        "status": "succeeded",
        "source_task_id": task_id,
        "predicted_rows": summary.row_count,
        "property_column_count": len(summary.property_columns),
    }
    report_path = report_dir / "report.json"
    write_json(report_path, report)

    result = {
        "result_version": "aidd.sciminer/result.v2",
        "artifacts": {
            "properties": {
                "name": f"{task_id}_molp_pc_admet_predictions",
                "type": "molecule_table@1",
                "files": {
                    "table_file": file_ref(
                        output_dir=output_dir,
                        path=target_csv,
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
                "name": f"{task_id}_molp_pc_adapter_report",
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
        "relations": [{"from": "report", "to": "properties", "type": "describes"}],
    }
    write_json(output_dir / "result.json", result)
    return result


def _first_existing(base_dir: Path, candidates: tuple[str, ...]) -> Path:
    for candidate in candidates:
        path = base_dir / candidate
        if path.is_file():
            return path
    searched = ", ".join(candidates)
    raise FileNotFoundError(f"Missing MolP-PC prediction CSV; searched: {searched}")
