"""Command-line entrypoint for standardized MolP-PC execution."""

from __future__ import annotations

import argparse
import traceback
from pathlib import Path
from typing import Any

from .contracts import RunRequest
from .csv_contract import inspect_molecule_table
from .io import read_json, resolve_task_file, write_json
from .legacy_predict import run_legacy_predict
from .result_builder import write_standard_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MolP-PC and emit platform result.v2")
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
        inspect_molecule_table(request.input_csv)
        legacy_csv = run_legacy_predict(
            model_root=Path(args.model_root).resolve(),
            input_csv=request.input_csv,
            work_dir=Path(args.work_dir).resolve(),
            device=request.device,
        )
        write_standard_result(
            request=_request_payload_for_result(payload, request),
            raw_output_dir=legacy_csv.parent,
            output_dir=output_dir,
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
) -> RunRequest:
    """Normalize standard request.v1 and legacy params.json into one runtime request."""
    parameters = payload.get("parameters") or payload.get("params") or {}
    task = payload.get("task") or {}
    tool_slug = str(task.get("tool_slug") or payload.get("task_name") or "molp-pc")
    tool_version = str(task.get("tool_version") or payload.get("tool_version") or "0.1.0")
    task_id = str(task_id_override or task.get("id") or payload.get("task_id") or "unknown-task")
    device = str(device_override or parameters.get("device") or "cpu")

    if payload.get("request_version") == "aidd.sciminer/request.v1":
        table_ref = (
            payload.get("inputs", {})
            .get("molecules", {})
            .get("files", {})
            .get("table_file", {})
            .get("path")
        )
        if not table_ref:
            raise ValueError("Standard request must include inputs.molecules.files.table_file.path")
        input_csv = resolve_task_file(str(table_ref), input_dir=input_dir)
    else:
        input_files = payload.get("input_files") or {}
        table_ref = input_files.get("smiles_csv")
        if table_ref:
            input_csv = resolve_task_file(str(table_ref), input_dir=input_dir)
        else:
            candidates = sorted(input_dir.glob("*.csv"))
            if len(candidates) != 1:
                raise ValueError(
                    "Legacy params must include input_files.smiles_csv or input-dir must "
                    "contain exactly one CSV"
                )
            input_csv = candidates[0].resolve()

    return RunRequest(
        task_id=task_id,
        tool_slug=tool_slug,
        tool_version=tool_version,
        input_csv=input_csv,
        device=device,
        parameters=parameters,
    )


def write_failure_result(*, output_dir: Path, error: Exception) -> None:
    write_json(
        output_dir / "result.json",
        {
            "success": False,
            "message": "MolP-PC property prediction failed",
            "error": {
                "code": "MODEL_EXECUTION_FAILED",
                "details": f"{type(error).__name__}: {error}",
            },
        },
    )


def _request_payload_for_result(payload: dict[str, Any], request: RunRequest) -> dict[str, Any]:
    if payload.get("task"):
        return payload
    return {
        "task": {
            "id": request.task_id,
            "tool_slug": request.tool_slug,
            "tool_version": request.tool_version,
        },
        "parameters": request.parameters,
    }


if __name__ == "__main__":
    raise SystemExit(main())
