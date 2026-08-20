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
    tool_contract_to_agent_summary,
)
from app.api.v1.tool_route_utils import build_validated_tool_contract


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
