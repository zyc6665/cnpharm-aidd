from datetime import datetime
from types import SimpleNamespace
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.capabilities import AIDD_TOOL_CAPABILITIES
from app.agents.aidd.plan_schema import parse_model_plan
from app.agents.aidd.registry import capability_to_tool_summary
from app.services.tool_contracts import (
    build_tool_contract,
    collect_tool_contract_validation_errors,
    contract_emits_standard_artifacts,
    tool_contract_to_agent_summary,
)
from app.api.v1.tool_route_utils import (
    build_validated_tool_contract,
    sanitize_public_tool_config,
    sanitize_public_tool_contract,
)
from app.schemas.tools import ToolPublicResponse, ToolVersionPublicResponse


def _v2_manifest(*, agent_exposure: bool = True) -> dict:
    return {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": "lvpocket-standard",
            "name": "LVpocket Standard",
            "version": "1.0.0",
            "description": "Standard pocket adapter",
        },
        "artifacts": {
            "inputs": [{"name": "protein", "type": "protein_structure@1", "required": True}],
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
            "properties": {"threshold": {"type": "number"}},
        },
        "exposure": {"agent": agent_exposure, "workflow": True, "direct_run": True},
        "variants": [
            {
                "name": "cpu",
                "accelerator": "cpu",
                "executor_types": ["cli"],
                "entrypoint": ["/app/runner/entrypoint.sh"],
            }
        ],
    }


def test_build_tool_contract_normalizes_identity_executor_schema_and_capability():
    tool = SimpleNamespace(
        id="tool-1",
        slug="gcdm-pocket-generation",
        name="GCDM Pocket Generation",
        description="Generate ligands from a pocket",
        status="published",
        is_public=True,
        current_version=SimpleNamespace(
            id="version-1",
            version="1.0.0",
            config={
                "type": "ssh_job",
                "timeout_sec": 3600,
                "input_schema": {
                    "type": "object",
                    "properties": {"pocket_pdb": {"type": "string"}},
                    "required": ["pocket_pdb"],
                },
                "output_schema": {"type": "object", "properties": {"success": {"type": "boolean"}}},
                "agent_capability": {
                    "enabled": True,
                    "stage": "molecule_generation",
                    "capability": "molecule_generation",
                    "inputs": [
                        {
                            "semantic_type": "pocket_pdb",
                            "field": "input_files.pocket_pdb",
                            "required": True,
                        }
                    ],
                    "outputs": [
                        {
                            "semantic_type": "generated_ligand",
                            "source": "output_files",
                            "match": {"extension": ".sdf"},
                        }
                    ],
                    "defaults": {"params.n_samples": 8},
                },
            },
        ),
    )

    contract = build_tool_contract(tool)

    assert contract["contract_version"] == "1.0"
    assert contract["id"] == "tool-1"
    assert contract["slug"] == "gcdm-pocket-generation"
    assert contract["executor"] == {"type": "ssh_job", "timeout_sec": 3600}
    assert contract["schema"]["input"]["required"] == ["pocket_pdb"]
    assert contract["schema"]["output"]["properties"]["success"]["type"] == "boolean"
    assert contract["capability"]["enabled"] is True
    assert contract["capability"]["inputs"][0]["semantic_type"] == "binding_pocket@1"
    assert contract["capability"]["outputs"][0]["semantic_type"] == "ligand_structure@1"


def test_public_tool_config_preserves_schemas_and_removes_nested_runtime_fields():
    config = {
        "input_schema": {
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "default": "must-not-be-exposed",
                    "x-api-token": "nested-secret",
                },
                "token_label": {"type": "string"},
            },
            "default": "visible",
        },
        "output_schema": {"type": "object"},
        "headers": {"Authorization": "Bearer secret"},
        "endpoint": "https://internal.example/invoke",
        "runtime": {
            "script_content": "private script",
            "api_token": "nested-secret",
            "image": "registry.example/tool@sha256:abc",
            "command": ["/private/runner"],
        },
    }

    public = sanitize_public_tool_config(config)

    assert public["input_schema"]["properties"]["token"]["type"] == "string"
    assert public["input_schema"]["properties"]["token_label"] == {"type": "string"}
    assert "default" not in public["input_schema"]["properties"]["token"]
    assert "x-api-token" not in public["input_schema"]["properties"]["token"]
    assert public["output_schema"] == config["output_schema"]
    assert "headers" not in public
    assert "endpoint" not in public
    assert public["runtime"] == {}


def test_public_tool_contract_omits_runtime_variants_and_nested_secrets():
    contract = {
        "executor": {"type": "docker", "timeout_sec": 60},
        "schema": {"input": {"type": "object"}, "output": {}},
        "variants": [{"image": "private.registry/tool", "entrypoint": ["run.sh"]}],
        "capability": {"defaults": {"params.threshold": 0.5, "api_token": "secret"}},
    }

    public = sanitize_public_tool_contract(contract)

    assert public["executor"] == {"type": "docker", "timeout_sec": 60}
    assert public["schema"] == contract["schema"]
    assert "variants" not in public
    assert public["capability"]["defaults"] == {"params.threshold": 0.5}


def test_public_tool_schema_excludes_runtime_version_config():
    timestamp = datetime(2026, 9, 24)
    tool = SimpleNamespace(
        id="tool-public",
        owner_id="owner-1",
        name="Public Tool",
        slug="public-tool",
        description="safe",
        category_id=None,
        category=None,
        icon=None,
        icon_url=None,
        status="published",
        is_public=True,
        current_version_id="version-1",
        gpu_required=False,
        gpu_memory_mb=0,
        timeout_sec=60,
        tags=[],
        current_version=SimpleNamespace(
            id="version-1",
            tool_id="tool-public",
            version="1.0.0",
            changelog=None,
            notes=None,
            config={"endpoint": "https://private.example"},
            is_active=True,
            deprecated=False,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        contract=None,
        statistics=None,
        created_at=timestamp,
        updated_at=timestamp,
    )

    payload = ToolPublicResponse.model_validate(tool).model_dump()
    assert isinstance(payload["current_version"], dict)
    assert "config" not in payload["current_version"]
    assert "config" not in ToolVersionPublicResponse.model_fields


def test_agent_tool_summary_keeps_legacy_tool_slug_but_exposes_contract_slug():
    summary = capability_to_tool_summary(AIDD_TOOL_CAPABILITIES["gcdm-pocket-generation"])

    assert summary["slug"] == "gcdm-pocket-generation"
    assert summary["tool_slug"] == "gcdm-pocket-generation"
    assert summary["capability"] == "molecule_generation"
    assert summary["inputs"] == ["binding_pocket@1"]
    assert summary["outputs"] == ["ligand_structure@1", "molecule_table@1"]


def test_tool_contract_normalizes_legacy_semantic_aliases():
    tool = SimpleNamespace(
        id="tool-legacy",
        slug="legacy-pocket-tool",
        name="Legacy Pocket Tool",
        description="Old workflow naming",
        status="published",
        is_public=True,
        current_version=SimpleNamespace(
            id="version-legacy",
            version="1.0.0",
            config={
                "type": "remote_api",
                "timeout_sec": 600,
                "input_schema": {"type": "object", "properties": {"protein_pdb": {"type": "string"}}},
                "output_schema": {"type": "object", "properties": {"success": {"type": "boolean"}}},
                "agent_capability": {
                    "enabled": True,
                    "stage": "pocket_exploration",
                    "capability": "pocket_prediction",
                    "inputs": [
                        {"semantic_type": "protein_structure", "field": "protein_pdb"},
                    ],
                    "outputs": [
                        {"semantic_type": "pocket_structure", "source": "output_files"},
                    ],
                },
            },
        ),
    )

    contract = build_tool_contract(tool)

    assert contract["capability"]["inputs"][0]["semantic_type"] == "protein_structure@1"
    assert contract["capability"]["outputs"][0]["semantic_type"] == "binding_pocket@1"


def test_contract_emits_standard_artifacts_uses_normalized_outputs():
    artifact_contract = {
        "artifacts": {
            "outputs": [{"name": "pocket", "type": "binding_pocket@1"}],
        },
        "capability": {"outputs": []},
    }
    capability_contract = {
        "artifacts": {"outputs": []},
        "capability": {
            "outputs": [
                {
                    "semantic_type": "generated_ligand",
                    "source": "output_files",
                }
            ]
        },
    }
    unknown_contract = {
        "artifacts": {"outputs": [{"name": "custom", "type": "custom@1"}]},
        "capability": {
            "outputs": [{"semantic_type": "custom@1", "source": "output_files"}]
        },
    }

    assert contract_emits_standard_artifacts(artifact_contract) is True
    assert contract_emits_standard_artifacts(capability_contract) is True
    assert contract_emits_standard_artifacts(unknown_contract) is False


def test_tool_package_v2_contract_exposes_standard_artifact_slots_without_mappings():
    tool = SimpleNamespace(
        id="tool-v2",
        slug="lvpocket-standard",
        name="LVpocket Standard",
        description="Standard pocket adapter",
        status="published",
        is_public=True,
        current_version=SimpleNamespace(
            id="version-v2",
            version="1.0.0",
            is_active=True,
            deprecated=False,
            config={"type": "python_script", "tool_package_manifest": _v2_manifest()},
        ),
    )

    contract = build_tool_contract(tool)

    assert contract["artifacts"]["inputs"] == [
        {"name": "protein", "type": "protein_structure@1", "required": True}
    ]
    assert contract["artifacts"]["outputs"][0] == {
        "name": "pocket",
        "type": "binding_pocket@1",
        "cardinality": "one",
        "required": True,
    }
    assert contract["exposure"] == {"agent": True, "workflow": True, "direct_run": True}
    assert contract["schema"]["input"]["properties"]["threshold"]["type"] == "number"
    assert contract["capability"]["inputs"][0] == {
        "semantic_type": "protein_structure@1",
        "field": "protein",
        "required": True,
        "accepted_extensions": [],
    }
    assert contract["capability"]["outputs"][0]["semantic_type"] == "binding_pocket@1"
    assert contract["capability"]["outputs"][0]["source"] == "artifact"
    assert contract["capability"]["outputs"][0]["match"] == {"type": "binding_pocket@1"}


def test_builtin_tool_contract_exposes_configured_standard_artifact_slots():
    tool = SimpleNamespace(
        id="tool-rdkit",
        slug="builtin-rdkit-properties",
        name="AIDD Rdkit Properties",
        description="Platform built-in RDKit descriptors",
        status="published",
        is_public=False,
        current_version=SimpleNamespace(
            id="version-rdkit",
            version="1.0.0",
            is_active=True,
            deprecated=False,
            config={
                "type": "builtin",
                "builtin_slug": "builtin-rdkit-properties",
                "timeout_sec": 120,
                "resource_profile": {
                    "tier": "light",
                    "cpu": 2,
                    "memory_mb": 2048,
                    "gpu": False,
                },
                "agent_capability": {
                    "enabled": True,
                    "stage": "property_prediction",
                    "capability": "property_prediction",
                    "inputs": [
                        {"semantic_type": "smiles_csv", "field": "smiles_csv", "required": True},
                    ],
                    "outputs": [
                        {
                            "semantic_type": "property_report",
                            "source": "output_files",
                            "required": True,
                        }
                    ],
                    "defaults": {"smiles_field": "SMILES"},
                },
                "artifacts": {
                    "inputs": [
                        {"name": "molecules", "type": "molecule_table@1", "required": True},
                    ],
                    "outputs": [
                        {"name": "properties", "type": "molecule_table@1", "required": True},
                        {"name": "report", "type": "run_report@1", "required": False},
                    ],
                },
            },
        ),
    )

    contract = build_tool_contract(tool)
    summary = tool_contract_to_agent_summary(contract)

    assert contract["artifacts"]["inputs"] == [
        {"name": "molecules", "type": "molecule_table@1", "required": True}
    ]
    assert contract["artifacts"]["outputs"] == [
        {"name": "properties", "type": "molecule_table@1", "cardinality": "one", "required": True},
        {"name": "report", "type": "run_report@1", "cardinality": "one", "required": False},
    ]
    assert summary["artifact_inputs"] == contract["artifacts"]["inputs"]
    assert summary["artifact_outputs"] == contract["artifacts"]["outputs"]
    assert summary["resource_profile"] == {
        "tier": "light",
        "cpu": 2,
        "memory_mb": 2048,
        "gpu": False,
    }


def test_tool_contract_preserves_artifact_output_provided_roles():
    tool = SimpleNamespace(
        id="tool-prep",
        slug="remote-protein-prep-api",
        name="Remote Protein Prep",
        description="Role-aware preparation adapter",
        status="published",
        is_public=True,
        current_version=SimpleNamespace(
            id="version-prep",
            version="1.0.0",
            is_active=True,
            deprecated=False,
            config={
                "type": "remote_api",
                "endpoint": "https://prep.example.com/invoke",
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {"type": "object", "properties": {}},
                "artifacts": {
                    "inputs": [
                        {"name": "protein", "type": "protein_structure@1", "required": True},
                    ],
                    "outputs": [
                        {
                            "name": "prepared_protein",
                            "type": "protein_structure@1",
                            "required": True,
                            "provided_roles": ["prepared_pdb", "receptor_pdbqt"],
                        },
                    ],
                },
            },
        ),
    )

    contract = build_tool_contract(tool)
    summary = tool_contract_to_agent_summary(contract)

    assert contract["artifacts"]["outputs"] == [
        {
            "name": "prepared_protein",
            "type": "protein_structure@1",
            "cardinality": "one",
            "required": True,
            "provided_roles": ["prepared_pdb", "receptor_pdbqt"],
        }
    ]
    assert summary["artifact_outputs"] == contract["artifacts"]["outputs"]


def test_tool_contract_validation_rejects_artifact_roles_from_another_type():
    errors = collect_tool_contract_validation_errors(
        SimpleNamespace(
            slug="bad-role-tool",
            current_version=SimpleNamespace(
                is_active=True,
                config={
                    "type": "remote_api",
                    "endpoint": "https://example.com/invoke",
                    "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}},
                    "output_schema": {"type": "object", "properties": {}},
                    "artifacts": {
                        "inputs": [
                            {
                                "name": "protein",
                                "type": "protein_structure@1",
                                "role_preferences": ["structure_file", "structure_3d_sdf"],
                            }
                        ],
                        "outputs": [
                            {
                                "name": "pocket",
                                "type": "binding_pocket@1",
                                "provided_roles": ["receptor_pdbqt"],
                            }
                        ],
                    },
                },
            ),
        )
    )

    assert any("artifacts.inputs[0].role_preferences" in error for error in errors)
    assert any("artifacts.outputs[0].provided_roles" in error for error in errors)


def test_lvpocket_legacy_contract_infers_role_aware_protein_slot():
    tool = SimpleNamespace(
        id="tool-lvpocket",
        slug="lvpocket-pocket-prediction",
        name="LVpocket",
        description="Legacy LVpocket ssh_job tool",
        status="published",
        is_public=True,
        current_version=SimpleNamespace(
            id="version-lvpocket",
            version="1.0.0",
            is_active=True,
            deprecated=False,
            config={
                "type": "ssh_job",
                "timeout_sec": 3600,
                "agent_capability": {
                    "enabled": True,
                    "stage": "pocket_exploration",
                    "capability": "pocket_prediction",
                    "inputs": [
                        {
                            "semantic_type": "protein_pdb",
                            "field": "protein_pdb",
                            "required": True,
                        }
                    ],
                    "outputs": [
                        {
                            "semantic_type": "pocket_pdb",
                            "source": "output_files",
                            "required": True,
                        }
                    ],
                    "defaults": {},
                },
            },
        ),
    )

    contract = build_tool_contract(tool)

    assert contract["artifacts"]["inputs"] == [
        {
            "name": "protein",
            "type": "protein_structure@1",
            "required": True,
            "role_preferences": ["prepared_pdb", "structure_file"],
            "readiness_policy": "prefer_prepared_warn_raw",
            "suggested_preparation_tool": "builtin-protein-preparation",
        }
    ]


def test_lvpocket_legacy_artifact_only_contract_is_workflow_executable():
    tool = SimpleNamespace(
        id="tool-lvpocket",
        slug="lvpocket-pocket-prediction",
        name="LVpocket",
        description="Legacy LVpocket ssh_job tool with artifact-only workflow metadata",
        status="published",
        is_public=True,
        current_version=SimpleNamespace(
            id="version-lvpocket",
            version="1.0.0",
            is_active=True,
            deprecated=False,
            config={
                "type": "ssh_job",
                "timeout_sec": 3600,
                "artifacts": {
                    "inputs": [
                        {
                            "name": "protein",
                            "type": "protein_structure@1",
                            "required": True,
                            "role_preferences": ["prepared_pdb", "structure_file"],
                        }
                    ],
                    "outputs": [
                        {"name": "pocket", "type": "binding_pocket@1", "required": True}
                    ],
                },
            },
        ),
    )

    contract = build_tool_contract(tool)
    errors = collect_tool_contract_validation_errors(tool)

    assert errors == []
    assert contract["capability"] == {
        "enabled": True,
        "capability": "pocket_prediction",
        "stage": "pocket_exploration",
        "inputs": [
            {
                "semantic_type": "protein_structure@1",
                "field": "protein",
                "required": True,
                "accepted_extensions": [],
            }
        ],
        "outputs": [
            {
                "semantic_type": "binding_pocket@1",
                "source": "artifact",
                "match": {"type": "binding_pocket@1"},
                "path": "pocket",
                "required": True,
            }
        ],
        "defaults": {},
        "virtual": False,
    }


def test_parameter_only_builtin_fetch_contract_is_valid_and_executable():
    tool = SimpleNamespace(
        id="tool-fetch-pdb",
        slug="builtin-fetch-pdb",
        name="Fetch PDB Structure",
        description="Download a protein structure from RCSB PDB",
        status="published",
        is_public=True,
        current_version=SimpleNamespace(
            id="version-fetch-pdb",
            version="1.0.0",
            is_active=True,
            deprecated=False,
            config={
                "type": "builtin",
                "builtin_slug": "builtin-fetch-pdb",
                "timeout_sec": 120,
                "input_schema": {
                    "type": "object",
                    "properties": {"pdb_id": {"type": "string"}},
                    "required": ["pdb_id"],
                },
                "agent_capability": {
                    "enabled": True,
                    "stage": "data_acquisition",
                    "capability": "external_database_fetch",
                    "inputs": [],
                    "outputs": [
                        {
                            "semantic_type": "protein_structure@1",
                            "source": "artifact",
                            "path": "protein",
                            "required": True,
                        }
                    ],
                    "defaults": {},
                },
                "artifacts": {
                    "inputs": [],
                    "outputs": [
                        {"name": "protein", "type": "protein_structure@1", "required": True},
                        {"name": "report", "type": "run_report@1", "required": False},
                    ],
                },
            },
        ),
    )

    assert collect_tool_contract_validation_errors(tool) == []
    contract = build_validated_tool_contract(tool)

    assert contract["validation"] == {"status": "valid", "errors": []}
    assert contract["capability"]["inputs"] == []
    assert contract["capability"]["outputs"][0]["source"] == "artifact"


def test_planner_available_tools_use_contract_slug_as_source_of_truth():
    plan = parse_model_plan(
        """
        {
          "intent": "property_prediction",
          "steps": [
            {
              "step_key": "predict_property",
              "capability": "property_prediction",
              "tool_slug": "molp-pc-property-prediction",
              "inputs": {"smiles_csv": "agent_input"},
              "params": {}
            }
          ]
        }
        """,
        available_tools=[
            {
                "slug": "molp-pc-property-prediction",
                "capability": "property_prediction",
                "outputs": ["property_report"],
            }
        ],
    )

    assert plan.steps[0].tool_slug == "molp-pc-property-prediction"


def test_contract_validation_reports_enabled_capability_shape_errors():
    tool = SimpleNamespace(
        id="tool-invalid",
        slug="invalid-workflow-tool",
        name="Invalid Workflow Tool",
        description="Broken agent capability",
        status="draft",
        is_public=False,
        current_version=SimpleNamespace(
            id="version-invalid",
            version="0.1.0",
            is_active=True,
            deprecated=False,
            config={
                "type": "remote_api",
                "timeout_sec": 120,
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {"type": "object", "properties": {}},
                "agent_capability": {
                    "enabled": True,
                    "capability": "",
                    "stage": "",
                    "inputs": [],
                    "outputs": [],
                },
            },
        ),
    )

    errors = collect_tool_contract_validation_errors(tool)

    assert any("agent_capability.capability" in error for error in errors)
    assert any("agent_capability.stage" in error for error in errors)
    assert any("agent_capability.inputs" in error for error in errors)
    assert any("agent_capability.outputs" in error for error in errors)
