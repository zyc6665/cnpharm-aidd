"""Load a Tool Package manifest from a package directory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.tool_packages.schemas import ToolPackageManifest


class ToolPackageLoadError(ValueError):
    """Raised when package files cannot be loaded into a manifest."""


def load_tool_package(package_dir: str | Path) -> ToolPackageManifest:
    root = Path(package_dir).resolve()
    manifest_path = root / "tool.yaml"
    if not manifest_path.is_file():
        raise ToolPackageLoadError(f"Tool Package 缺少 {manifest_path.name}")

    raw = _read_yaml_object(manifest_path)
    raw["variants"] = [_load_variant(root, item) for item in raw.get("variants", [])]
    try:
        return ToolPackageManifest.model_validate(raw)
    except ValidationError as exc:
        raise ToolPackageLoadError(f"tool.yaml 不符合 Tool Package v1：{exc}") from exc


def _load_variant(root: Path, item: Any) -> Any:
    if isinstance(item, str):
        return _read_variant_file(root, item)
    if isinstance(item, dict) and set(item) == {"file"}:
        return _read_variant_file(root, item["file"])
    return item


def _read_variant_file(root: Path, relative_path: Any) -> dict[str, Any]:
    if not isinstance(relative_path, str) or not relative_path:
        raise ToolPackageLoadError("variant file 必须是相对路径")
    path = (root / relative_path).resolve()
    if root not in path.parents:
        raise ToolPackageLoadError("variant file 不得位于 Tool Package 目录之外")
    if not path.is_file():
        raise ToolPackageLoadError(f"variant file 不存在：{relative_path}")
    return _read_yaml_object(path)


def _read_yaml_object(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ToolPackageLoadError(f"无法读取 {path.name}：{exc}") from exc
    if not isinstance(value, dict):
        raise ToolPackageLoadError(f"{path.name} 顶层必须是对象")
    return value

