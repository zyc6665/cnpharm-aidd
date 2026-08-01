"""Adapt MolP-PC legacy prediction outputs to platform result.v2."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


LEGACY_PREDICTION_FILENAME = "cb_data_result.csv"
STANDARD_PREDICTION_FILENAME = "molp_pc_predictions.csv"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Adapt MolP-PC legacy output CSV to standard result.v2"
    )
    parser.add_argument("--request", required=True, help="Standard request.v1 JSON")
    parser.add_argument(
        "--raw-output-dir",
        required=True,
        help="Directory containing legacy MolP-PC outputs",
    )
    parser.add_argument("--output-dir", required=True, help="Platform task output directory")
    args = parser.parse_args()

    request = _read_json(Path(args.request))
    result = adapt_legacy_outputs(
        request=request,
        raw_output_dir=Path(args.raw_output_dir),
        output_dir=Path(args.output_dir),
    )
    _write_json(Path(args.output_dir) / "result.json", result)
    return 0


def adapt_legacy_outputs(
    *,
    request: dict[str, Any],
    raw_output_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Convert a MolP-PC prediction CSV into standard molecule_table@1 outputs."""
    task = request.get("task") or {}
    task_id = str(task.get("id") or "unknown-task")
    tool_slug = str(task.get("tool_slug") or "molp-pc-property-prediction")
    properties_dir = output_dir / "artifacts" / "properties"
    report_dir = output_dir / "reports"
    properties_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    source_csv = raw_output_dir / LEGACY_PREDICTION_FILENAME
    if not source_csv.is_file():
        raise FileNotFoundError(f"Missing MolP-PC prediction CSV: {source_csv}")

    prediction_summary = _inspect_prediction_csv(source_csv)
    target_csv = properties_dir / STANDARD_PREDICTION_FILENAME
    shutil.copyfile(source_csv, target_csv)

    metadata = {
        "molecule_id_field": "SMILES",
        "source_task_id": task_id,
        "source_input_ref": "input:molecules",
        "row_count": prediction_summary["row_count"],
        "property_column_count": len(prediction_summary["property_columns"]),
        "property_columns": prediction_summary["property_columns"],
        "model_name": "MolP-PC",
    }
    metadata_path = properties_dir / "metadata.json"
    _write_json(metadata_path, metadata)

    report = {
        "tool": tool_slug,
        "adapter": "tool-package-v2",
        "status": "succeeded",
        "source_task_id": task_id,
        "predicted_rows": prediction_summary["row_count"],
        "property_column_count": len(prediction_summary["property_columns"]),
    }
    report_path = report_dir / "report.json"
    _write_json(report_path, report)

    return {
        "result_version": "aidd.sciminer/result.v2",
        "artifacts": {
            "properties": {
                "name": f"{task_id}_molp_pc_admet_predictions",
                "type": "molecule_table@1",
                "files": {
                    "table_file": _file_ref(
                        output_dir=output_dir,
                        path=target_csv,
                        content_type="text/csv",
                    ),
                    "metadata_json": _file_ref(
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
                    "report_json": _file_ref(
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


def _inspect_prediction_csv(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if "SMILES" not in fieldnames:
            raise ValueError(f"MolP-PC prediction CSV must contain SMILES column: {path}")
        rows = list(reader)
    property_columns = [column for column in fieldnames if column != "SMILES"]
    if not property_columns:
        raise ValueError(f"MolP-PC prediction CSV must contain property columns: {path}")
    return {"row_count": len(rows), "property_columns": property_columns}


def _file_ref(*, output_dir: Path, path: Path, content_type: str) -> dict[str, str]:
    relative = path.resolve().relative_to(output_dir.resolve()).as_posix()
    return {
        "path": relative,
        "sha256": _sha256_file(path),
        "content_type": content_type,
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
