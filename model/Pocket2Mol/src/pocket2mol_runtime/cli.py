"""Command-line entrypoint for standardized Pocket2Mol execution."""

from __future__ import annotations

import argparse
import os
import subprocess
import traceback
from pathlib import Path
from typing import Any

from .io import read_json, resolve_task_file, write_json
from .result_builder import write_standard_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Pocket2Mol and emit platform result.v2")
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--task-id", default="")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--params-json", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).resolve()
    work_dir = Path(args.work_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        payload = read_json(Path(args.params_json))
        input_dir = Path(args.input_dir).resolve()
        legacy_payload = build_legacy_payload(payload, input_dir=input_dir)
        legacy_params_json = work_dir / "legacy-params.json"
        write_json(legacy_params_json, legacy_payload)
        legacy_output_dir = work_dir / "legacy-output"
        legacy_work_dir = work_dir / "legacy-work"
        legacy_output_dir.mkdir(parents=True, exist_ok=True)
        legacy_work_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                str(_legacy_entrypoint(Path(args.model_root))),
                "--task-id",
                str(args.task_id or _task_id(payload)),
                "--input-dir",
                str(input_dir),
                "--output-dir",
                str(legacy_output_dir),
                "--params-json",
                str(legacy_params_json),
                "--work-dir",
                str(legacy_work_dir),
                "--device",
                str(args.device or legacy_payload["params"].get("device") or "auto"),
            ],
            check=True,
        )
        write_standard_result(
            request=_request_payload_for_result(payload),
            raw_output_dir=legacy_output_dir,
            output_dir=output_dir,
        )
    except Exception as exc:  # pragma: no cover - exercised in deployed runtime
        traceback.print_exc()
        write_failure_result(output_dir=output_dir, error=exc)
        return 1
    return 0


def build_legacy_payload(payload: dict[str, Any], *, input_dir: Path) -> dict[str, Any]:
    parameters = dict(payload.get("parameters") or payload.get("params") or {})
    if payload.get("request_version") != "aidd.sciminer/request.v1":
        return {
            "task_name": payload.get("task_name", "pocket2mol_pdb_sampling"),
            "params": parameters,
            "input_files": dict(payload.get("input_files") or {}),
        }

    pocket_file = _standard_pocket_file(payload, input_dir=input_dir)
    pocket_metadata = (
        payload.get("inputs", {})
        .get("pocket", {})
        .get("metadata", {})
    )
    if "center" not in parameters and isinstance(pocket_metadata, dict):
        center = _format_center(pocket_metadata.get("center"))
        if center:
            parameters["center"] = center
    return {
        "task_name": "pocket2mol_pdb_sampling",
        "params": parameters,
        "input_files": {"protein_pdb": _legacy_input_ref(pocket_file, input_dir=input_dir)},
    }


def write_failure_result(*, output_dir: Path, error: Exception) -> None:
    write_json(
        output_dir / "result.json",
        {
            "success": False,
            "message": "Pocket2Mol ligand generation failed",
            "error": {
                "code": "MODEL_EXECUTION_FAILED",
                "details": f"{type(error).__name__}: {error}",
            },
        },
    )


def _standard_pocket_file(payload: dict[str, Any], *, input_dir: Path) -> Path:
    files = (
        payload.get("inputs", {})
        .get("pocket", {})
        .get("files", {})
    )
    for role in ("residue_pocket_pdb", "atom_pocket_pdb"):
        ref = files.get(role, {}) if isinstance(files, dict) else {}
        if isinstance(ref, dict) and ref.get("path"):
            return resolve_task_file(str(ref["path"]), input_dir=input_dir)
    raise ValueError("Standard request must include inputs.pocket PDB file roles")


def _format_center(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list) and len(value) == 3:
        return ",".join(str(item) for item in value)
    return None


def _legacy_input_ref(path: Path, *, input_dir: Path) -> str:
    try:
        return path.resolve().relative_to(input_dir.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _legacy_entrypoint(model_root: Path) -> Path:
    configured = os.environ.get("POCKET2MOL_LEGACY_ENTRYPOINT")
    if configured:
        return Path(configured).resolve()
    return (model_root / "legacy" / "platform_run.sh").resolve()


def _task_id(payload: dict[str, Any]) -> str:
    return str((payload.get("task") or {}).get("id") or payload.get("task_id") or "unknown-task")


def _request_payload_for_result(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("task"):
        return payload
    return {
        "task": {
            "id": _task_id(payload),
            "tool_slug": "pocket2mol-pocket-ligand-generation",
            "tool_version": "0.1.2",
        },
        "parameters": payload.get("parameters") or payload.get("params") or {},
    }


if __name__ == "__main__":
    raise SystemExit(main())
