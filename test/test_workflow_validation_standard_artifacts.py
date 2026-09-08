"""Workflow validation tests for standard Artifact slots."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.exceptions import ValidationException  # noqa: E402
from app.services.workflow_scheduler import initial_node_states  # noqa: E402
from app.services.workflow_validation import (  # noqa: E402
    required_workflow_inputs,
    validate_workflow_definition,
)


def _definition() -> dict:
    return {
        "nodes": [
            {
                "id": "input-protein_structure@1",
                "kind": "input",
                "standard_type": "protein_structure@1",
            },
            {
                "id": "pocket_prediction",
                "kind": "tool",
                "tool_slug": "standard-pocket-tool",
                "artifact_input_slots": [
                    {"name": "protein", "type": "protein_structure@1", "required": True}
                ],
                "artifact_inputs": {"protein": "workflow_input:protein_structure@1"},
                "artifact_outputs": [
                    {"name": "pocket", "type": "binding_pocket@1", "required": True}
                ],
            },
            {
                "id": "molecule_generation",
                "kind": "tool",
                "tool_slug": "standard-generation-tool",
                "artifact_input_slots": [
                    {"name": "pocket", "type": "binding_pocket@1", "required": True}
                ],
                "artifact_inputs": {"pocket": "node:pocket_prediction:pocket"},
                "artifact_outputs": [
                    {
                        "name": "ligands",
                        "type": "ligand_structure@1",
                        "cardinality": "many",
                        "required": True,
                    }
                ],
            },
        ],
        "edges": [
            {
                "source": "input-protein_structure@1",
                "target": "pocket_prediction",
                "source_output": "protein_structure@1",
                "target_input": "protein",
            },
            {
                "source": "pocket_prediction",
                "target": "molecule_generation",
                "source_output": "pocket",
                "target_input": "pocket",
            },
        ],
    }


def _at003_definition() -> dict:
    return {
        "nodes": [
            {
                "id": "fetch_pubchem",
                "kind": "tool",
                "tool_slug": "builtin-fetch-ligand",
                "artifact_outputs": [
                    {"name": "ligand", "type": "ligand_structure@1", "required": True},
                    {"name": "report", "type": "run_report@1", "required": False},
                ],
            },
            {
                "id": "ligand_preparation",
                "kind": "tool",
                "tool_slug": "ligand-preparation",
                "artifact_input_slots": [
                    {"name": "ligand", "type": "ligand_structure@1", "required": True}
                ],
                "artifact_inputs": {"ligand": "node:fetch_pubchem:ligand"},
                "artifact_outputs": [
                    {"name": "ligand", "type": "ligand_structure@1", "required": True},
                    {"name": "report", "type": "run_report@1", "required": False},
                ],
            },
            {
                "id": "sdf_to_smiles",
                "kind": "tool",
                "tool_slug": "builtin-sdf-to-smiles-csv",
                "artifact_input_slots": [
                    {"name": "ligand", "type": "ligand_structure@1", "required": True}
                ],
                "artifact_inputs": {"ligand": "node:ligand_preparation:ligand"},
                "artifact_outputs": [
                    {"name": "molecules", "type": "molecule_table@1", "required": True}
                ],
            },
            {
                "id": "rdkit_properties",
                "kind": "tool",
                "tool_slug": "builtin-rdkit-properties",
                "artifact_input_slots": [
                    {"name": "molecules", "type": "molecule_table@1", "required": True}
                ],
                "artifact_inputs": {"molecules": "node:sdf_to_smiles:molecules"},
                "artifact_outputs": [
                    {"name": "properties", "type": "molecule_table@1", "required": True},
                    {"name": "report", "type": "run_report@1", "required": False},
                ],
            },
            {
                "id": "molp_pc_admet",
                "kind": "tool",
                "tool_slug": "molp-pc-property-prediction",
                "artifact_input_slots": [
                    {"name": "molecules", "type": "molecule_table@1", "required": True}
                ],
                "artifact_inputs": {"molecules": "node:rdkit_properties:properties"},
                "artifact_outputs": [
                    {"name": "properties", "type": "molecule_table@1", "required": True},
                    {"name": "report", "type": "run_report@1", "required": True},
                ],
            },
            {
                "id": "result_admet",
                "kind": "result",
                "artifact_input_slots": [
                    {"name": "report", "type": "run_report@1", "required": True}
                ],
                "artifact_inputs": {"report": "node:molp_pc_admet:report"},
            },
        ],
        "edges": [
            {"source": "fetch_pubchem", "target": "ligand_preparation"},
            {"source": "ligand_preparation", "target": "sdf_to_smiles"},
            {"source": "sdf_to_smiles", "target": "rdkit_properties"},
            {"source": "rdkit_properties", "target": "molp_pc_admet"},
            {"source": "molp_pc_admet", "target": "result_admet"},
        ],
    }


def test_validate_workflow_definition_accepts_standard_artifact_slots():
    assert validate_workflow_definition(_definition()) == [
        "pocket_prediction",
        "molecule_generation",
    ]
    assert required_workflow_inputs(_definition()) == {"protein_structure@1"}


def test_validate_workflow_definition_rejects_missing_required_artifact_input():
    definition = _definition()
    definition["nodes"][1]["artifact_inputs"] = {}

    with pytest.raises(ValidationException, match="missing required artifact input"):
        validate_workflow_definition(definition)


def test_validate_workflow_definition_rejects_standard_type_mismatch():
    definition = _definition()
    definition["nodes"][2]["artifact_input_slots"] = [
        {"name": "pocket", "type": "protein_structure@1", "required": True}
    ]

    with pytest.raises(ValidationException, match="type mismatch"):
        validate_workflow_definition(definition)


def test_validate_workflow_definition_rejects_unknown_artifact_output_slot():
    definition = _definition()
    definition["nodes"][2]["artifact_inputs"] = {"pocket": "node:pocket_prediction:missing"}

    with pytest.raises(ValidationException, match="unknown artifact output"):
        validate_workflow_definition(definition)


def test_initial_node_states_preserves_standard_artifact_slots():
    states = initial_node_states(_definition(), ["pocket_prediction", "molecule_generation"])

    assert states["pocket_prediction"]["artifact_inputs"] == {
        "protein": "workflow_input:protein_structure@1"
    }
    assert states["pocket_prediction"]["artifact_input_slots"] == [
        {"name": "protein", "type": "protein_structure@1", "required": True}
    ]
    assert states["molecule_generation"]["artifact_outputs"][0]["type"] == "ligand_structure@1"


def test_at003_definition_accepts_standard_artifact_bindings():
    execution_order = validate_workflow_definition(_at003_definition())
    states = initial_node_states(_at003_definition(), execution_order)

    assert execution_order == [
        "fetch_pubchem",
        "ligand_preparation",
        "sdf_to_smiles",
        "rdkit_properties",
        "molp_pc_admet",
    ]
    assert required_workflow_inputs(_at003_definition()) == set()
    assert states["molp_pc_admet"]["artifact_inputs"] == {
        "molecules": "node:rdkit_properties:properties"
    }
    assert states["molp_pc_admet"]["artifact_outputs"][-1] == {
        "name": "report",
        "type": "run_report@1",
        "required": True,
    }
    assert "result_admet" not in states
