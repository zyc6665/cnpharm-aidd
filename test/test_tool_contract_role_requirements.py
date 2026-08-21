"""Role-aware standard Artifact input contract tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.remote_tools.schemas import RemoteToolManifest  # noqa: E402
from app.services.tool_contracts import build_tool_contract  # noqa: E402
from app.tool_packages.schemas import ToolPackageV2Manifest  # noqa: E402


ROLE_AWARE_INPUT = {
    "name": "protein",
    "type": "protein_structure@1",
    "required": True,
    "role_preferences": ["prepared_pdb", "structure_file"],
    "required_roles": [],
    "readiness_policy": "prefer_prepared_warn_raw",
    "suggested_preparation_tool": "builtin-protein-preparation",
}


def _minimal_tool_package_v2_manifest() -> dict:
    return {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": "role-aware-pocket",
            "name": "Role Aware Pocket",
            "version": "1.0.0",
        },
        "artifacts": {
            "inputs": [dict(ROLE_AWARE_INPUT)],
            "outputs": [
                {
                    "name": "pocket",
                    "type": "binding_pocket@1",
                    "cardinality": "one",
                    "required": True,
                }
            ],
        },
        "parameters_schema": {"type": "object", "properties": {}},
        "runtime": {
            "python": "3.10",
            "executor_support": ["ssh_docker_exec"],
            "selection_policy": "test fixture",
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": "registry.example/sciminer/role-aware-pocket:1.0.0",
                    "image_digest": f"sha256:{'a' * 64}",
                },
                "fallback": {
                    "kind": "conda_pack",
                    "uri": "artifacts://model-envs/role-aware-pocket/1.0.0/env.tar.gz",
                    "sha256": "b" * 64,
                },
            },
            "weights": {
                "manifest_uri": "artifacts://model-weights/role-aware-pocket/1.0.0/weights.json",
                "manifest_sha256": "c" * 64,
            },
            "cache_policy": {"key_fields": ["metadata.slug"], "mutable_host_paths_forbidden": True},
        },
        "variants": [
            {
                "name": "cpu",
                "accelerator": "cpu",
                "executor_types": ["cli"],
                "entrypoint": ["/app/runner/entrypoint.sh"],
            }
        ],
    }


def _minimal_remote_tool_manifest() -> dict:
    return {
        "api_version": "aidd.sciminer/remote-tool.v1",
        "kind": "RemoteTool",
        "metadata": {
            "slug": "role-aware-remote-pocket",
            "name": "Role Aware Remote Pocket",
            "version": "1.0.0",
            "description": "Pocket prediction service",
        },
        "artifacts": {
            "inputs": [dict(ROLE_AWARE_INPUT)],
            "outputs": [
                {
                    "name": "pocket",
                    "type": "binding_pocket@1",
                    "cardinality": "one",
                    "required": True,
                }
            ],
        },
        "parameters_schema": {"type": "object", "properties": {}},
        "endpoints": {
            "invoke": "/invoke",
            "status": "/runs/{remote_run_id}",
            "logs": "/runs/{remote_run_id}/logs",
            "cancel": "/runs/{remote_run_id}/cancel",
            "artifacts": "/runs/{remote_run_id}/artifacts",
        },
        "capabilities": {"async": True, "logs": True, "cancel": True, "progress": True},
    }


def test_tool_package_v2_artifact_inputs_accept_role_requirements() -> None:
    manifest = ToolPackageV2Manifest.model_validate(_minimal_tool_package_v2_manifest())
    input_slot = manifest.artifacts.inputs[0]

    assert input_slot.role_preferences == ["prepared_pdb", "structure_file"]
    assert input_slot.required_roles == []
    assert input_slot.readiness_policy == "prefer_prepared_warn_raw"
    assert input_slot.suggested_preparation_tool == "builtin-protein-preparation"


def test_remote_tool_artifact_inputs_accept_role_requirements() -> None:
    manifest = RemoteToolManifest.model_validate(_minimal_remote_tool_manifest())
    input_slot = manifest.artifacts.inputs[0]

    assert input_slot.role_preferences == ["prepared_pdb", "structure_file"]
    assert input_slot.required_roles == []
    assert input_slot.readiness_policy == "prefer_prepared_warn_raw"
    assert input_slot.suggested_preparation_tool == "builtin-protein-preparation"


def test_tool_contract_projects_role_requirements_to_artifact_inputs() -> None:
    manifest = _minimal_tool_package_v2_manifest()
    tool = SimpleNamespace(
        id="tool-1",
        slug="role-aware-pocket",
        name="Role Aware Pocket",
        description=None,
        status="published",
        is_public=True,
        current_version=SimpleNamespace(
            id="version-1",
            version="1.0.0",
            is_active=True,
            deprecated=False,
            validation_status="valid",
            validation_errors=[],
            manifest=manifest,
        ),
    )

    contract = build_tool_contract(tool)

    assert contract["artifacts"]["inputs"][0] == ROLE_AWARE_INPUT
