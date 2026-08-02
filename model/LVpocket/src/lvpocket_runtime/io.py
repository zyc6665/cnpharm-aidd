"""Small file helpers for the LVpocket runtime adapter."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_ref(*, output_dir: Path, path: Path, content_type: str) -> dict[str, str]:
    relative = path.resolve().relative_to(output_dir.resolve()).as_posix()
    return {
        "path": relative,
        "sha256": sha256_file(path),
        "content_type": content_type,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
