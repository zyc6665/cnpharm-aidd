"""I/O helpers for the MolP-PC runtime wrapper."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_ref(*, output_dir: Path, path: Path, content_type: str) -> dict[str, str]:
    relative = path.resolve().relative_to(output_dir.resolve()).as_posix()
    return {
        "path": relative,
        "sha256": sha256_file(path),
        "content_type": content_type,
    }


def resolve_task_file(raw_path: str, *, input_dir: Path) -> Path:
    """Resolve a platform-provided relative file path under the task input area."""
    raw = Path(raw_path)
    if raw.is_absolute():
        return raw
    normalized = raw_path.replace("\\", "/").strip()
    parsed = PurePosixPath(normalized)
    if not normalized or any(part in {"", ".", ".."} for part in parsed.parts):
        raise ValueError(f"Unsafe task file path: {raw_path}")

    task_root = input_dir.parent
    candidates = [task_root / parsed.as_posix(), input_dir / parsed.as_posix()]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()
