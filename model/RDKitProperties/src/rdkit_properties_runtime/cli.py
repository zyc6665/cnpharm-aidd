"""Command-line entrypoint for the RDKit properties runtime."""

from __future__ import annotations

import argparse
import traceback
from pathlib import Path
from typing import Any

from .io import read_json, resolve_task_file, write_json
from .properties import calculate_properties_table
from .result_builder import write_failure_result, write_standard_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run RDKit molecular properties and emit result.v2"
    )
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--task-id", default="")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--params-json", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--device", default="")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        payload = read_json(Path(args.params_json))
        request = build_run_request(
            payload=payload,
            input_dir=Path(args.input_dir).resolve(),
            task_id_override=args.task_id,
            device_override=args.device,
        )
        raw_output_dir = Path(args.work_dir).resolve() / "rdkit_properties"
        raw_output_dir.mkdir(parents=True, exist_ok=True)
        summary = calculate_properties_table(
            input_csv=request["input_csv"],
            output_csv=raw_output_dir / "rdkit_properties.csv",
            molecule_id_field=request["molecule_id_field"],
            smiles_field=request["smiles_field"],
        )
        write_standard_result(
            request=request["payload"],
            raw_output_dir=raw_output_dir,
            output_dir=output_dir,
            summary=summary.to_dict(),
        )
    except Exception as exc:  # pragma: no cover - exercised in deployed runtime
        traceback.print_exc()
        write_failure_result(output_dir=output_dir, error=exc)
        return 1
    return 0


def build_run_request(
    *,
    payload: dict[str, Any],
    input_dir: Path,
    task_id_override: str = "",
    device_override: str = "",
) -> dict[str, Any]:
    parameters = payload.get("parameters") or payload.get("params") or {}
    task = dict(payload.get("task") or {})
    task["id"] = str(task_id_override or task.get("id") or payload.get("task_id") or "unknown-task")
    task.setdefault("tool_slug", "rdkit-molecular-properties")
    task.setdefault("tool_version", "0.1.0")

    if device_override:
        parameters = {**parameters, "device": device_override}

    if payload.get("request_version") == "aidd.sciminer/request.v1":
        molecules = payload.get("inputs", {}).get("molecules", {})
        table_ref = molecules.get("files", {}).get("table_file", {}).get("path")
        metadata = molecules.get("metadata") or {}
        if not table_ref:
            raise ValueError("Standard request must include inputs.molecules.files.table_file.path")
        input_csv = resolve_task_file(str(table_ref), input_dir=input_dir)
        molecule_id_field = str(metadata.get("molecule_id_field") or "molecule_id")
    else:
        input_files = payload.get("input_files") or {}
        table_ref = input_files.get("molecules_csv") or input_files.get("input_csv")
        if not table_ref:
            candidates = sorted(input_dir.glob("*.csv"))
            if len(candidates) != 1:
                raise ValueError(
                    "Legacy params must include input_files.molecules_csv or input-dir must "
                    "contain exactly one CSV"
                )
            table_ref = str(candidates[0])
        input_csv = resolve_task_file(str(table_ref), input_dir=input_dir)
        molecule_id_field = str(parameters.get("molecule_id_field") or "molecule_id")

    request_payload = dict(payload)
    request_payload["task"] = task
    request_payload["parameters"] = parameters
    return {
        "payload": request_payload,
        "input_csv": input_csv,
        "molecule_id_field": molecule_id_field,
        "smiles_field": str(parameters.get("smiles_field") or "SMILES"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
