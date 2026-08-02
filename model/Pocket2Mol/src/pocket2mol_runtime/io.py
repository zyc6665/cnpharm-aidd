"""Small file helpers for Pocket2Mol runtime adapters."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def file_ref(*, output_dir: Path, path: Path, content_type: str) -> dict[str, str]:
    return {
        "path": path.relative_to(output_dir).as_posix(),
        "sha256": sha256_file(path),
        "content_type": content_type,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_task_file(path: str, *, input_dir: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    if candidate.parts and candidate.parts[0] == "input":
        return (input_dir.parent / candidate).resolve()
    return (input_dir / candidate).resolve()
