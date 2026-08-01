"""Template adapter from legacy model outputs to platform result.v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


POCKET_ROLE_FILES = {
    "residue_pocket_pdb": ("residue_pocket.pdb", "chemical/x-pdb"),
    "atom_pocket_pdb": ("atom_pocket.pdb", "chemical/x-pdb"),
    "pocket_metadata_json": ("pocket_metadata.json", "application/json"),
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Adapt legacy pocket model outputs to platform result.v2"
    )
    parser.add_argument("--request", required=True, help="Standard request.v1 JSON")
    parser.add_argument(
        "--raw-output-dir",
        required=True,
        help="Directory containing legacy model outputs after model execution",
    )
    parser.add_argument("--output-dir", required=True, help="Platform task output directory")
    args = parser.parse_args()

    request = _read_json(Path(args.request))
    result = adapt_legacy_outputs(
        request=request,
        raw_output_dir=Path(args.raw_output_dir),
        output_dir=Path(args.output_dir),
    )
    result_path = Path(args.output_dir) / "result.json"
    _write_json(result_path, result)
    return 0


def adapt_legacy_outputs(
    *,
    request: dict[str, Any],
    raw_output_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Convert one legacy pocket prediction run into standard platform artifacts."""
    task = request.get("task") or {}
    task_id = str(task.get("id") or "unknown-task")
    pocket_dir = output_dir / "artifacts" / "pocket"
    report_dir = output_dir / "reports"
    pocket_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    files = _copy_standard_pocket_files(raw_output_dir=raw_output_dir, pocket_dir=pocket_dir)
    metadata = _read_json(pocket_dir / "pocket_metadata.json")
    metadata.setdefault("source_protein_ref", "input:protein")

    report = {
        "tool": str(task.get("tool_slug") or "legacy-model"),
        "adapter": "tool-package-v2",
        "status": "succeeded",
        "source_task_id": task_id,
        "notes": [
            "Replace raw output collection and pocket conversion logic with model-specific code."
        ],
    }
    report_path = report_dir / "report.json"
    _write_json(report_path, report)

    return {
        "result_version": "aidd.sciminer/result.v2",
        "artifacts": {
            "pocket": {
                "name": f"{task_id}_binding_pocket",
                "type": "binding_pocket@1",
                "files": files,
                "metadata": metadata,
            },
            "report": {
                "name": f"{task_id}_adapter_report",
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
        "relations": [
            {"from": "pocket", "to": "report", "type": "validated_by"},
            {"from": "report", "to": "pocket", "type": "describes"},
        ],
    }


def _copy_standard_pocket_files(*, raw_output_dir: Path, pocket_dir: Path) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for role, (filename, content_type) in POCKET_ROLE_FILES.items():
        source = raw_output_dir / filename
        if not source.is_file():
            raise FileNotFoundError(
                f"Legacy adapter must produce {filename} before declaring {role}"
            )
        target = pocket_dir / filename
        shutil.copyfile(source, target)
        files[role] = _file_ref(
            output_dir=pocket_dir.parents[1],
            path=target,
            content_type=content_type,
        )
    return files


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
