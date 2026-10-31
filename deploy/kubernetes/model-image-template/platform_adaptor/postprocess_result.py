#!/usr/bin/env python3
"""Convert a legacy model result.json into the platform standard result.v2.

The model containers in this directory wrap upstream research scripts that emit a
legacy ``result.json`` (``success``/``outputs``/``artifacts``).  The platform
Kubernetes adaptor only accepts ``aidd.sciminer/result`` (result.v2), so after the
model entry finishes we translate the legacy payload into standard artifacts with
the file roles required by each artifact type.

Usage:
    python postprocess_result.py --model molp-pc --output-dir OUT --task-id ID
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_ref(output_dir: Path, relative: str) -> dict[str, str]:
    path = output_dir / relative
    if not path.is_file():
        raise SystemExit(f"declared output file is missing: {relative}")
    return {"path": relative, "sha256": sha256_file(path)}


def molecule_table_metadata(output_dir: Path, task_id: str, field: str) -> str:
    relative = "artifacts/metadata.json"
    write_json(
        output_dir / relative,
        {
            "molecule_id_field": field,
            "source_task_id": task_id,
            "generated_by": "platform_postprocess",
        },
    )
    return relative


def run_report(output_dir: Path, task_id: str, tool: str, summary: dict[str, Any]) -> str:
    relative = "artifacts/report.json"
    write_json(
        output_dir / relative,
        {"source_task_id": task_id, "tool": tool, "status": "succeeded", **summary},
    )
    return relative


def load_legacy(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "result.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("result_version") == "aidd.sciminer/result":
        raise SystemExit("result.json already uses result.v2")
    if not payload.get("success"):
        raise SystemExit("legacy result reports failure; no v2 payload to build")
    return payload


def flatten_prediction(prediction: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in prediction.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            row[key] = value
        elif isinstance(value, dict):
            for inner_key, inner_value in value.items():
                if isinstance(inner_value, (str, int, float, bool)) or inner_value is None:
                    row[f"{key}.{inner_key}"] = inner_value
    return row


def molp_pc(output_dir: Path, task_id: str, legacy: dict[str, Any]) -> dict[str, Any]:
    table = "artifacts/cb_data_result.csv"
    metadata = molecule_table_metadata(output_dir, task_id, "SMILES")
    report = run_report(output_dir, task_id, "molp-pc-property-prediction", legacy.get("outputs") or {})
    return {
        "result_version": "aidd.sciminer/result",
        "artifacts": {
            "properties": {
                "type": "molecule_table@1",
                "files": {
                    "table_file": file_ref(output_dir, table),
                    "metadata_json": file_ref(output_dir, metadata),
                },
                "metadata": {"molecule_id_field": "SMILES", "source_task_id": task_id},
            },
            "report": {
                "type": "run_report@1",
                "files": {"report_json": file_ref(output_dir, report)},
                "metadata": {"source_task_id": task_id},
            },
        },
        "metrics": legacy.get("metrics") or {},
    }


def msign(output_dir: Path, task_id: str, legacy: dict[str, Any]) -> dict[str, Any]:
    outputs = legacy.get("outputs") or {}
    rows: list[dict[str, Any]] = []
    predictions = outputs.get("predictions")
    if isinstance(predictions, list):
        for index, item in enumerate(predictions):
            row = flatten_prediction(item if isinstance(item, dict) else {})
            row.setdefault("molecule_id", str(item.get("complex_id") if isinstance(item, dict) else index))
            rows.append(row)
    else:
        prediction = outputs.get("prediction") if isinstance(outputs.get("prediction"), dict) else {}
        row = flatten_prediction(prediction)
        row.setdefault("molecule_id", str(outputs.get("complex_id") or "complex_1"))
        rows.append(row)
    if not rows:
        raise SystemExit("MSIGN legacy result has no prediction rows")

    table = "artifacts/affinity.csv"
    fieldnames = sorted({key for row in rows for key in row})
    with (output_dir / table).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    metadata = molecule_table_metadata(output_dir, task_id, "molecule_id")
    report = run_report(output_dir, task_id, "msign-affinity-prediction", outputs)
    return {
        "result_version": "aidd.sciminer/result",
        "artifacts": {
            "affinity": {
                "type": "molecule_table@1",
                "files": {
                    "table_file": file_ref(output_dir, table),
                    "metadata_json": file_ref(output_dir, metadata),
                },
                "metadata": {"molecule_id_field": "molecule_id", "source_task_id": task_id},
            },
            "report": {
                "type": "run_report@1",
                "files": {"report_json": file_ref(output_dir, report)},
                "metadata": {"source_task_id": task_id},
            },
        },
        "metrics": legacy.get("metrics") or {},
    }


def pocket2mol(output_dir: Path, task_id: str, legacy: dict[str, Any]) -> dict[str, Any]:
    outputs = legacy.get("outputs") or {}
    table = str(outputs.get("smiles_file") or "artifacts/SMILES.txt")
    sdf = str(outputs.get("combined_sdf") or "artifacts/generated_molecules.sdf")
    metadata = molecule_table_metadata(output_dir, task_id, "smiles")
    report = run_report(output_dir, task_id, "pocket2mol-pocket-ligand-generation", outputs)
    return {
        "result_version": "aidd.sciminer/result",
        "artifacts": {
            "molecules": {
                "type": "molecule_table@1",
                "files": {
                    "table_file": file_ref(output_dir, table),
                    "metadata_json": file_ref(output_dir, metadata),
                },
                "metadata": {"molecule_id_field": "smiles", "source_task_id": task_id},
            },
            "ligands": {
                "type": "ligand_structure@1",
                "files": {"structure_file": file_ref(output_dir, sdf)},
            },
            "report": {
                "type": "run_report@1",
                "files": {"report_json": file_ref(output_dir, report)},
                "metadata": {"source_task_id": task_id},
            },
        },
        "metrics": legacy.get("metrics") or {},
    }


BUILDERS = {"molp-pc": molp_pc, "msign": msign, "pocket2mol": pocket2mol}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=sorted(BUILDERS))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--task-id", default="unknown")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    legacy = load_legacy(output_dir)
    (output_dir / "result.legacy.json").write_text(
        json.dumps(legacy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    payload = BUILDERS[args.model](output_dir, args.task_id, legacy)
    (output_dir / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
