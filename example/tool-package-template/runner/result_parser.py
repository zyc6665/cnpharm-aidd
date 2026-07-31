"""Validate the result envelope emitted by a packaged tool implementation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def parse_result(result_path: Path, output_root: Path) -> dict[str, Any]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    schema = json.loads(
        (PACKAGE_ROOT / "schemas" / "outputs.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(result)

    root = output_root.resolve()
    for artifact in result.values():
        artifact_path = (root / artifact["path"]).resolve()
        if root not in artifact_path.parents:
            raise ValueError(f"Artifact path escapes output directory: {artifact['path']}")
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Artifact does not exist: {artifact['path']}")
        digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if digest != artifact["sha256"]:
            raise ValueError(f"Artifact checksum mismatch: {artifact['path']}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    parse_result(args.result, args.output_root)


if __name__ == "__main__":
    main()
