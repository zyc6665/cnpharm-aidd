from __future__ import annotations

import pytest

from app.tool_packages.config_resolver import (
    ToolPackageConfigError,
    tool_package_manifest_data,
    validated_tool_package_manifest,
    validated_tool_package_manifest_data,
)


def _minimal_v2_manifest() -> dict:
    return {
        "api_version": "aidd.sciminer/tool-package",
        "kind": "ToolPackage",
        "metadata": {
            "slug": "molp-pc",
            "name": "MolP-PC",
            "version": "1.0.0",
            "description": "Predict molecule properties",
        },
        "artifacts": {
            "inputs": [{"name": "molecules", "type": "molecule_table@1"}],
            "outputs": [{"name": "properties", "type": "molecule_table@1"}],
        },
        "parameters_schema": {"type": "object", "properties": {}},
        "runtime": {
            "python": "3.11",
            "executor_support": ["ssh_docker_exec"],
            "selection_policy": "prefer_cpu",
            "artifacts": {
                "primary": {"kind": "container", "image": "registry/molp-pc:1.0.0"},
                "fallback": {"kind": "container", "image": "registry/molp-pc:1.0.0"},
            },
            "weights": {
                "manifest_uri": "s3://weights/molp-pc/manifest.json",
                "manifest_sha256": "a" * 64,
            },
            "cache_policy": {
                "key_fields": ["metadata.slug", "metadata.version"],
            },
        },
        "variants": [
            {
                "name": "cpu",
                "accelerator": "cpu",
                "executor_types": ["cli"],
                "entrypoint": ["python", "runner.py"],
            }
        ],
    }


def test_tool_package_manifest_data_reads_supported_config_shapes() -> None:
    manifest = _minimal_v2_manifest()

    assert tool_package_manifest_data({"tool_package_manifest": manifest}) is manifest
    assert tool_package_manifest_data({"tool_package": {"manifest": manifest}}) is manifest


def test_validated_tool_package_manifest_data_ignores_non_v2_manifests() -> None:
    legacy_manifest = {"api_version": "aidd.sciminer/v1", "kind": "ToolPackage"}

    assert validated_tool_package_manifest_data({"tool_package_manifest": legacy_manifest}) is None
    assert validated_tool_package_manifest_data({"tool_package_manifest": "bad"}) is None
    assert validated_tool_package_manifest_data(None) is None


def test_validated_tool_package_manifest_parses_valid_manifest() -> None:
    manifest = validated_tool_package_manifest({"tool_package_manifest": _minimal_v2_manifest()})

    assert manifest is not None
    assert manifest.metadata.slug == "molp-pc"
    assert manifest.artifacts.inputs[0].name == "molecules"


def test_validated_tool_package_manifest_wraps_invalid_manifest_errors() -> None:
    invalid_manifest = _minimal_v2_manifest()
    invalid_manifest.pop("runtime")

    with pytest.raises(ToolPackageConfigError, match="Invalid Tool Package v2 manifest"):
        validated_tool_package_manifest({"tool_package_manifest": invalid_manifest})


def test_validated_tool_package_manifest_can_ignore_invalid_manifest() -> None:
    invalid_manifest = _minimal_v2_manifest()
    invalid_manifest.pop("runtime")

    assert validated_tool_package_manifest(
        {"tool_package_manifest": invalid_manifest},
        ignore_invalid=True,
    ) is None
