"""Validate the artifact envelope emitted by an LVpocket remote job."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def parse_result(result_path: Path, output_root: Path) -> dict[str, Any]:
    if not result_path.is_file():
        raise FileNotFoundError(f"Required result.json does not exist: {result_path}")

    result = json.loads(result_path.read_text(encoding="utf-8"))
    schema = json.loads(
        (PACKAGE_ROOT / "schemas" / "outputs.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(result)

    root = output_root.resolve()
    for artifact in result.values():
        relative_path = artifact["path"]
        artifact_path = (root / relative_path).resolve()
        if root not in artifact_path.parents:
            raise ValueError(f"Artifact path escapes output directory: {relative_path}")
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Artifact does not exist: {relative_path}")
        digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if digest != artifact["sha256"]:
            raise ValueError(f"Artifact checksum mismatch: {relative_path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate LVpocket result artifacts")
    parser.add_argument("result", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    parse_result(args.result, args.output_root)


if __name__ == "__main__":
    main()
