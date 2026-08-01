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
