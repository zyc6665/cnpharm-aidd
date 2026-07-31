"""Replace this reference implementation with the packaged scientific tool."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _write_artifact(path: Path, content: str) -> dict[str, str]:
    path.write_text(content, encoding="utf-8")
    return {
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    threshold = request.get("parameters", {}).get("confidence_threshold", 0.5)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pockets = _write_artifact(
        args.output_dir / "pockets.json",
        json.dumps({"pockets": [], "confidence_threshold": threshold}),
    )
    report = _write_artifact(
        args.output_dir / "run-report.json",
        json.dumps({"status": "succeeded", "implementation": "template"}),
    )
    result = {
        "pockets": {"artifact_type": "pocket_result", **pockets},
        "report": {"artifact_type": "run_report", **report},
    }
    (args.output_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")


if __name__ == "__main__":
    main()
