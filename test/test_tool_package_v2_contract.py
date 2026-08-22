"""Tool Package v2 standard Artifact contract tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tool_packages.loader import load_tool_package
from app.tool_packages.schemas import ToolPackageV2Manifest
from app.tool_packages.validator import validate_tool_package


def _v2_manifest() -> dict:
    return {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": "lvpocket-standard",
            "name": "LVpocket Standard",
            "version": "1.0.0",
        },
        "artifacts": {
            "inputs": [
                {"name": "protein", "type": "protein_structure@1", "required": True}
            ],
            "outputs": [
                {
                    "name": "pocket",
                    "type": "binding_pocket@1",
                    "cardinality": "one",
                    "required": True,
                },
                {
                    "name": "report",
                    "type": "run_report@1",
                    "cardinality": "one",
                    "required": False,
                },
            ],
        },
        "parameters_schema": {
            "type": "object",
            "properties": {"threshold": {"type": "number", "default": 0.5}},
        },
        "adapter": {
            "input": [{"input": "protein", "method": "direct_file_mount"}],
            "output": [
                {
                    "output": "pocket",
                    "method": "voxel_to_standard_binding_pocket",
                    "validator_profile": "binding_pocket_v1_core",
                }
            ],
        },
        "exposure": {"agent": True, "workflow": True, "direct_run": True},
        "runtime": {
            "python": "3.10",
            "cuda": "11.8",
            "executor_support": ["ssh_docker_exec", "slurm", "k8s_job"],
            "selection_policy": (
                "prefer container image by immutable digest; fallback to conda_pack"
            ),
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": "registry.example/sciminer/lvpocket-runtime:1.0.0",
                    "image_digest": f"sha256:{'a' * 64}",
                    "includes": ["python", "cuda_runtime", "dependencies"],
                },
                "fallback": {
                    "kind": "conda_pack",
                    "uri": "artifacts://model-envs/lvpocket-standard/1.0.0/env.tar.gz",
                    "sha256": "b" * 64,
                    "includes": ["python", "dependencies"],
                },
            },
            "weights": {
                "manifest_uri": "artifacts://model-weights/lvpocket-standard/1.0.0/weights.json",
                "manifest_sha256": "c" * 64,
            },
            "cache_policy": {
                "key_fields": [
                    "metadata.slug",
                    "metadata.version",
                    "runtime.artifacts.selected.digest_or_sha256",
                    "runtime.weights.manifest_sha256",
                ],
                "mutable_host_paths_forbidden": True,
            },
        },
        "variants": [
            {
                "name": "cuda",
                "accelerator": "nvidia_cuda",
                "executor_types": ["container", "remote_job"],
                "image": "registry.local/lvpocket:1.0.0-cuda",
                "entrypoint": ["/app/runner/entrypoint.sh"],
                "resources": {
                    "cpu": 4,
                    "memory_mb": 16384,
                    "devices": ["nvidia.com/gpu"],
                    "driver": ">=535",
                },
                "validation_status": "validated",
            }
        ],
    }


def test_v2_manifest_accepts_standard_artifact_refs_and_cardinality():
    manifest = ToolPackageV2Manifest.model_validate(_v2_manifest())
    result = validate_tool_package(manifest)

    assert manifest.artifacts.inputs[0].type == "protein_structure@1"
    assert manifest.artifacts.outputs[0].cardinality == "one"
    assert manifest.runtime.artifacts.primary.image_digest == f"sha256:{'a' * 64}"
    assert result.is_valid is True


def test_v2_manifest_preserves_artifact_output_provided_roles():
    raw = _v2_manifest()
    raw["artifacts"]["outputs"][0]["provided_roles"] = ["atom_pocket_pdb", "pocket_metadata_json"]

    manifest = ToolPackageV2Manifest.model_validate(raw)

    assert manifest.artifacts.outputs[0].provided_roles == ["atom_pocket_pdb", "pocket_metadata_json"]


def test_v2_manifest_rejects_output_roles_from_another_artifact_type():
    raw = _v2_manifest()
    raw["artifacts"]["outputs"][0]["provided_roles"] = ["receptor_pdbqt"]

    with pytest.raises(ValidationError) as exc_info:
        ToolPackageV2Manifest.model_validate(raw)

    assert "Unknown file role" in str(exc_info.value)


def test_v2_manifest_requires_runtime_env_metadata():
    raw = _v2_manifest()
    raw.pop("runtime")

    with pytest.raises(ValidationError):
        ToolPackageV2Manifest.model_validate(raw)


def test_v2_validator_rejects_runtime_without_immutable_image_digest():
    raw = _v2_manifest()
    raw["runtime"]["artifacts"]["primary"]["image_digest"] = ""
    manifest = ToolPackageV2Manifest.model_validate(raw)

    result = validate_tool_package(manifest)

    assert result.is_valid is False
    assert any("image_digest" in error and "sha256" in error for error in result.errors)


def test_v2_validator_rejects_runtime_without_fallback_sha256():
    raw = _v2_manifest()
    raw["runtime"]["artifacts"]["fallback"]["sha256"] = ""
    manifest = ToolPackageV2Manifest.model_validate(raw)

    result = validate_tool_package(manifest)

    assert result.is_valid is False
    assert any("fallback" in error and "sha256" in error for error in result.errors)


def test_v2_validator_rejects_runtime_without_weight_manifest_sha256():
    raw = _v2_manifest()
    raw["runtime"]["weights"]["manifest_sha256"] = ""
    manifest = ToolPackageV2Manifest.model_validate(raw)

    result = validate_tool_package(manifest)

    assert result.is_valid is False
    assert any("weights" in error and "sha256" in error for error in result.errors)


def test_v2_manifest_rejects_legacy_semantic_artifact_fields():
    raw = _v2_manifest()
    raw["artifacts"]["inputs"][0] = {
        "name": "protein",
        "semantic_type": "protein_structure",
        "artifact_type": "protein_structure",
    }

    with pytest.raises(ValidationError):
        ToolPackageV2Manifest.model_validate(raw)


def test_v2_validator_rejects_unknown_standard_artifact_type():
    raw = _v2_manifest()
    raw["artifacts"]["outputs"][0]["type"] = "pocket_pdb"
    manifest = ToolPackageV2Manifest.model_validate(raw)

    result = validate_tool_package(manifest)

    assert result.is_valid is False
    assert any("pocket_pdb" in error and "standard" in error for error in result.errors)


def test_v2_validator_rejects_device_as_required_business_parameter():
    raw = _v2_manifest()
    raw["parameters_schema"] = {
        "type": "object",
        "properties": {"device": {"type": "string"}},
        "required": ["device"],
    }
    manifest = ToolPackageV2Manifest.model_validate(raw)

    result = validate_tool_package(manifest)

    assert result.is_valid is False
    assert any("device" in error and "variant" in error for error in result.errors)


def test_loader_detects_v2_manifest(tmp_path: Path):
    import yaml

    (tmp_path / "tool.yaml").write_text(
        yaml.safe_dump(_v2_manifest(), sort_keys=False),
        encoding="utf-8",
    )

    manifest = load_tool_package(tmp_path)

    assert isinstance(manifest, ToolPackageV2Manifest)
    assert manifest.api_version == "aidd.sciminer/tool-package.v2"
