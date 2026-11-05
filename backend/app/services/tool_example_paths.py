"""Path and preview helpers for tool example files."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from app.common.exceptions import ValidationException


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEXT_PREVIEW_EXTENSIONS = {
    ".txt",
    ".json",
    ".csv",
    ".fasta",
    ".fa",
    ".pdb",
    ".log",
    ".md",
}
EXAMPLE_PREVIEW_MAX_BYTES = 64 * 1024

_EXAMPLE_BASE_DIR_INDEX: dict[Path, dict[str, Path]] = {}


def resolve_tool_example_base_dir(
    tool: Any,
    config: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
) -> Path:
    configured_base = config.get("example_base_dir")
    if isinstance(configured_base, str) and configured_base.strip():
        base_path = Path(configured_base)
        if not base_path.is_absolute():
            base_path = project_root / base_path
        return base_path.resolve()

    example_root = (project_root / "example").resolve()
    slug_index = _get_example_base_dir_index(example_root)
    if tool.slug in slug_index:
        return slug_index[tool.slug]

    return (example_root / tool.slug).resolve()


def resolve_tool_example_file_path(base_dir: Path, relative_path: str) -> Path:
    candidate = (base_dir / relative_path).resolve()
    try:
        candidate.relative_to(base_dir)
    except ValueError as exc:
        raise ValidationException("示例文件路径非法") from exc
    return candidate


_CONTENT_TYPE_OVERRIDES = {
    # Windows 注册表通常没有 .pdb 的 MIME 映射，显式补齐以保证跨平台一致。
    ".pdb": "chemical/x-pdb",
}


def guess_tool_example_content_type(path: Path) -> str:
    override = _CONTENT_TYPE_OVERRIDES.get(path.suffix.lower())
    if override:
        return override
    content_type, _ = mimetypes.guess_type(path.name)
    return content_type or "application/octet-stream"


def is_previewable_tool_example_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_PREVIEW_EXTENSIONS


def _get_example_base_dir_index(example_root: Path) -> dict[str, Path]:
    cached_index = _EXAMPLE_BASE_DIR_INDEX.get(example_root)
    if cached_index is not None:
        return cached_index

    slug_index: dict[str, Path] = {}
    for config_path in example_root.rglob("platform_tool*.json"):
        try:
            with config_path.open("r", encoding="utf-8") as config_file:
                raw_config = json.load(config_file)
        except (OSError, ValueError):
            continue
        slug = raw_config.get("slug")
        if isinstance(slug, str) and slug.strip():
            slug_index.setdefault(slug, config_path.parent.resolve())

    _EXAMPLE_BASE_DIR_INDEX[example_root] = slug_index
    return slug_index
