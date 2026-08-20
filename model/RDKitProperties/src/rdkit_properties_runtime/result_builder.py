"""Build standard result.v2 envelopes for RDKit properties."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .io import file_ref, write_json


def write_standard_result(
    *,
    request: dict[str, Any],
    raw_output_dir: Path,
    output_dir: Path,
    summary: dict[str, Any],
) -> dict[str, Any]:
    task = request.get("task") or {}
    task_id = str(task.get("id") or request.get("task_id") or "unknown-task")
    tool_slug = str(task.get("tool_slug") or "rdkit-molecular-properties")

    properties_dir = output_dir / "artifacts" / "properties"
    report_dir = output_dir / "reports"
    properties_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    source_csv = raw_output_dir / "rdkit_properties.csv"
    target_csv = properties_dir / "rdkit_properties.csv"
    shutil.copyfile(source_csv, target_csv)

    molecules = (request.get("inputs") or {}).get("molecules") or {}
    input_metadata = molecules.get("metadata") or {}
    metadata = {
        "molecule_id_field": str(input_metadata.get("molecule_id_field") or "molecule_id"),
        "source_task_id": task_id,
        "row_count": int(summary["row_count"]),
        "valid_molecule_count": int(summary["valid_molecule_count"]),
        "invalid_molecule_count": int(summary["invalid_molecule_count"]),
        "property_columns": list(summary["property_columns"]),
        "backend_name": str(summary["backend_name"]),
        "backend_version": str(summary["backend_version"]),
    }
    metadata_path = properties_dir / "metadata.json"
    write_json(metadata_path, metadata)

    report = {
        "tool": tool_slug,
        "adapter": "rdkit_properties_runtime",
        "status": "succeeded",
        "source_task_id": task_id,
        "row_count": metadata["row_count"],
        "valid_molecule_count": metadata["valid_molecule_count"],
        "invalid_molecule_count": metadata["invalid_molecule_count"],
        "backend_name": metadata["backend_name"],
        "backend_version": metadata["backend_version"],
    }
    report_path = report_dir / "report.json"
    write_json(report_path, report)

    result = {
        "result_version": "aidd.sciminer/result.v2",
        "artifacts": {
            "properties": {
                "name": f"{task_id}_rdkit_properties",
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
                "name": f"{task_id}_rdkit_properties_report",
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


def write_failure_result(*, output_dir: Path, error: Exception) -> None:
    report_dir = output_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "report.json"
    report = {
        "tool": "rdkit-molecular-properties",
        "adapter": "rdkit_properties_runtime",
        "status": "failed",
        "error": {
            "code": "MOLECULE_PROPERTIES_EXECUTION_FAILED",
            "details": f"{type(error).__name__}: {error}",
        },
    }
    write_json(report_path, report)
    write_json(
        output_dir / "result.json",
        {
            "result_version": "aidd.sciminer/result.v2",
            "artifacts": {
                "report": {
                    "name": "rdkit_properties_failure_report",
                    "type": "run_report@1",
                    "files": {
                        "report_json": file_ref(
                            output_dir=output_dir,
                            path=report_path,
                            content_type="application/json",
                        )
                    },
                    "metadata": {"status": "failed"},
                }
            },
            "summary": {"status": "failed"},
        },
    )
