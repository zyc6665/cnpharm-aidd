"""Command-line entrypoint for standardized LVpocket execution."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import traceback
from pathlib import Path
from typing import Any

from .io import read_json, write_json
from .result_builder import write_standard_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run LVpocket and emit platform result.v2")
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
        request = _request_payload_for_result(payload=payload, task_id=args.task_id)
        legacy_output_dir = work_dir / "legacy-output"
        legacy_work_dir = work_dir / "legacy-work"
        legacy_output_dir.mkdir(parents=True, exist_ok=True)
        legacy_work_dir.mkdir(parents=True, exist_ok=True)
        legacy_entrypoint = _legacy_entrypoint(Path(args.model_root))
        subprocess.run(
            [
                str(legacy_entrypoint),
                "--task-id",
                str(args.task_id or request["task"]["id"]),
                "--input-dir",
                str(Path(args.input_dir).resolve()),
                "--output-dir",
                str(legacy_output_dir),
                "--params-json",
                str(Path(args.params_json).resolve()),
                "--work-dir",
                str(legacy_work_dir),
                "--device",
                str(args.device or "auto"),
            ],
            check=True,
        )
        write_standard_result(
            request=request,
            raw_output_dir=legacy_output_dir,
            output_dir=output_dir,
        )
    except Exception as exc:  # pragma: no cover - exercised in deployed runtime
        traceback.print_exc()
        write_failure_result(output_dir=output_dir, error=exc)
        return 1
    return 0


def write_failure_result(*, output_dir: Path, error: Exception) -> None:
    write_json(
        output_dir / "result.json",
        {
            "success": False,
            "message": "LVpocket pocket prediction failed",
            "error": {
                "code": "MODEL_EXECUTION_FAILED",
                "details": f"{type(error).__name__}: {error}",
            },
        },
    )


def _legacy_entrypoint(model_root: Path) -> Path:
    configured = os.environ.get("LVPOCKET_LEGACY_ENTRYPOINT")
    if configured:
        return Path(configured).resolve()
    return (model_root / "legacy" / "platform_run.sh").resolve()


def _request_payload_for_result(*, payload: dict[str, Any], task_id: str) -> dict[str, Any]:
    if payload.get("task"):
        return payload
    parameters = payload.get("parameters") or payload.get("params") or payload
    return {
        "request_version": "aidd.sciminer/request.v1",
        "task": {
            "id": task_id or str(payload.get("task_id") or "unknown-task"),
            "tool_slug": "lvpocket-standard-pocket",
            "tool_version": "1.0.0",
        },
        "parameters": {
            "model_choice": parameters.get("model_choice", "auto"),
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
