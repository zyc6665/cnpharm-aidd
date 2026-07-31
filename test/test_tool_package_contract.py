"""Tool Package v1 contract loading and validation tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tool_packages.loader import ToolPackageLoadError, load_tool_package
from app.tool_packages.schemas import ToolPackageManifest
from app.tool_packages.validator import validate_tool_package
from app.tool_packages import validator as validator_module
from app.services.tool_contracts import build_tool_contract


def _manifest() -> dict:
    return {
        "api_version": "aidd.sciminer/v1",
        "kind": "ToolPackage",
        "metadata": {
            "slug": "pocket-finder",
            "name": "Pocket Finder",
            "version": "1.0.0",
            "description": "Detect ligandable pockets",
        },
        "artifacts": {
            "inputs": [
                {
                    "name": "protein",
                    "semantic_type": "protein_structure",
                    "artifact_type": "protein_structure",
                }
            ],
            "outputs": [
                {
                    "name": "pockets",
                    "semantic_type": "pocket_result",
                    "artifact_type": "pocket_result",
                }
            ],
        },
        "variants": [
            {
                "name": "cpu",
                "accelerator": "cpu",
                "executor_types": ["container", "cli"],
                "image": "registry.local/pocket-finder:1.0.0-cpu",
                "entrypoint": ["/app/run"],
                "resources": {"cpu": 4, "memory_mb": 8192},
                "validation_status": "validated",
                "inputs": ["protein_structure"],
                "outputs": ["pocket_result"],
            },
            {
                "name": "cuda",
                "accelerator": "nvidia_cuda",
                "executor_types": ["container", "remote_job"],
                "image": "registry.local/pocket-finder:1.0.0-cuda",
                "entrypoint": ["/app/run"],
                "resources": {
                    "cpu": 4,
                    "memory_mb": 16384,
                    "devices": ["nvidia.com/gpu"],
                    "driver": ">=535",
                },
                "validation_status": "validated",
                "inputs": ["protein_structure"],
                "outputs": ["pocket_result"],
            },
            {
                "name": "dcu",
                "accelerator": "haiguang_dcu",
                "executor_types": ["container", "remote_job"],
                "image": "registry.local/pocket-finder:1.0.0-dcu",
                "entrypoint": ["/app/run"],
                "resources": {
                    "cpu": 4,
                    "memory_mb": 16384,
                    "devices": ["hygon.com/dcu"],
                    "driver": ">=6.2",
                },
                "validation_status": "adapted_pending_hardware_validation",
                "inputs": ["protein_structure"],
                "outputs": ["pocket_result"],
            },
        ],
    }


def test_loader_requires_tool_yaml(tmp_path: Path):
    with pytest.raises(ToolPackageLoadError, match="tool.yaml"):
        load_tool_package(tmp_path)


def test_loader_reads_tool_yaml(tmp_path: Path):
    import yaml

    (tmp_path / "tool.yaml").write_text(
        yaml.safe_dump(_manifest(), sort_keys=False),
        encoding="utf-8",
    )

    package = load_tool_package(tmp_path)

    assert package.metadata.slug == "pocket-finder"
    assert [variant.accelerator.value for variant in package.variants] == [
        "cpu",
        "nvidia_cuda",
        "haiguang_dcu",
    ]


@pytest.mark.parametrize("direction", ["inputs", "outputs"])
def test_manifest_requires_semantic_inputs_and_outputs(direction: str):
    raw = _manifest()
    raw["artifacts"][direction] = []

    result = validate_tool_package(ToolPackageManifest.model_validate(raw))

    assert result.is_valid is False
    assert any(f"artifacts.{direction}" in error for error in result.errors)


def test_variant_cannot_reference_undeclared_artifact_type():
    raw = _manifest()
    raw["variants"][0]["outputs"] = ["docking_score"]

    result = validate_tool_package(ToolPackageManifest.model_validate(raw))

    assert any("docking_score" in error and "未声明" in error for error in result.errors)


def test_nvidia_variant_requires_device_and_driver_declarations():
    raw = _manifest()
    raw["variants"][1]["resources"].pop("devices")
    raw["variants"][1]["resources"].pop("driver")

    result = validate_tool_package(ToolPackageManifest.model_validate(raw))

    assert any("NVIDIA" in error and "devices" in error for error in result.errors)
    assert any("NVIDIA" in error and "driver" in error for error in result.errors)


def test_unverified_dcu_variant_cannot_claim_validated_support():
    raw = _manifest()
    raw["variants"][2]["validation_status"] = "validated"

    result = validate_tool_package(ToolPackageManifest.model_validate(raw))

    assert any("DCU" in error and "adapted_pending_hardware_validation" in error for error in result.errors)


def test_all_variants_must_expose_the_same_output_contract():
    raw = deepcopy(_manifest())
    raw["artifacts"]["outputs"].append(
        {"name": "report", "semantic_type": "run_report", "artifact_type": "run_report"}
    )
    raw["variants"][2]["outputs"] = ["pocket_result", "run_report"]

    result = validate_tool_package(ToolPackageManifest.model_validate(raw))

    assert any("输出契约" in error for error in result.errors)


def test_existing_tool_contract_builder_reads_tool_package_manifest():
    package = SimpleNamespace(
        id="package-id",
        slug="pocket-finder",
        name="Pocket Finder",
        description="Detect pockets",
        status="draft",
        current_version=SimpleNamespace(
            id="version-id",
            version="1.0.0",
            manifest=_manifest(),
            validation_status="valid",
            validation_errors=[],
        ),
    )

    contract = build_tool_contract(package)

    assert contract["contract_version"] == "1.0"
    assert contract["package"]["api_version"] == "aidd.sciminer/v1"
    assert {item["accelerator"] for item in contract["variants"]} == {
        "cpu",
        "nvidia_cuda",
        "haiguang_dcu",
    }
    assert contract["capability"]["inputs"][0]["semantic_type"] == "protein_structure"


def test_validator_cli_returns_nonzero_for_invalid_package(tmp_path: Path, capsys):
    exit_code = validator_module.main([str(tmp_path)])

    assert exit_code == 2
    assert "tool.yaml" in capsys.readouterr().err
