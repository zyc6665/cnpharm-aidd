"""Resolve Tool Package manifests stored in ToolVersion config."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.tool_packages.schemas import TOOL_PACKAGE_V2_API_VERSION, ToolPackageV2Manifest


class ToolPackageConfigError(ValueError):
    """Raised when a persisted Tool Package config is present but invalid."""


def tool_package_manifest_data(config: object) -> dict[str, Any] | None:
    """Return the raw manifest dict from supported ToolVersion config shapes."""
    if not isinstance(config, dict):
        return None

    manifest = config.get("tool_package_manifest")
    tool_package_config = config.get("tool_package")
    if not isinstance(manifest, dict) and isinstance(tool_package_config, dict):
        manifest = tool_package_config.get("manifest")
    return manifest if isinstance(manifest, dict) else None


def tool_package_declares_mock(config: object) -> bool:
    """Return whether the persisted manifest marks the package as a demo mock."""
    manifest = tool_package_manifest_data(config)
    if not manifest:
        return False
    metadata = manifest.get("metadata")
    return isinstance(metadata, dict) and metadata.get("mock") is True


def tool_package_v2_manifest_data(config: object) -> dict[str, Any] | None:
    manifest = tool_package_manifest_data(config)
    if manifest is None or manifest.get("api_version") != TOOL_PACKAGE_V2_API_VERSION:
        return None
    return manifest


def tool_package_v2_manifest(
    config: object,
    *,
    ignore_invalid: bool = False,
) -> ToolPackageV2Manifest | None:
    """Parse a Tool Package v2 manifest from config when present."""
    manifest = tool_package_v2_manifest_data(config)
    if manifest is None:
        return None

    try:
        return ToolPackageV2Manifest.model_validate(manifest)
    except ValidationError as exc:
        if ignore_invalid:
            return None
        raise ToolPackageConfigError(f"Invalid Tool Package v2 manifest: {exc}") from exc
