"""AIDD plan to workflow draft conversion tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.planner import AIDDPlan, AIDDPlanStep  # noqa: E402
from app.agents.aidd.workflow_drafts import (  # noqa: E402
    build_workflow_definition_from_plan,
)
from app.common.exceptions import ValidationException  # noqa: E402


def _plan(*steps: AIDDPlanStep) -> AIDDPlan:
    return AIDDPlan(
        intent="generate_molecules_from_protein",
        requested_outputs=["generated_ligand"],
        steps=list(steps),
    )


def _contract(
    *,
    tool_id: str,
    slug: str,
    version_id: str,
    outputs: list[str],
) -> dict:
    return {
        "id": tool_id,
        "slug": slug,
        "tool_slug": slug,
        "tool_version": {
            "id": version_id,
            "version": "1.0.0",
            "is_active": True,
            "deprecated": False,
        },
        "output_rules": [
            {"semantic_type": semantic_type, "source": "output_files", "required": True}
            for semantic_type in outputs
        ],
    }


def _standard_contract(
    *,
    tool_id: str,
    slug: str,
    version_id: str,
    inputs: list[dict],
    outputs: list[dict],
) -> dict:
    return {
        "id": tool_id,
        "slug": slug,
        "tool_slug": slug,
        "tool_version": {
            "id": version_id,
            "version": "1.0.0",
            "is_active": True,
            "deprecated": False,
        },
        "artifact_inputs": inputs,
        "artifact_outputs": outputs,
        "input_bindings": [
            {"semantic_type": item["type"], "field": item["name"], "required": item.get("required", True)}
            for item in inputs
        ],
        "output_rules": [
            {"semantic_type": item["type"], "source": "artifact", "required": item.get("required", True)}
            for item in outputs
        ],
    }


def test_build_workflow_definition_from_plan_preserves_executable_contract() -> None:
    plan = _plan(
        AIDDPlanStep(
            step_key="pocket_prediction",
            tool_slug="lvpocket-pocket-prediction",
            depends_on=[],
            inputs={"protein_pdb": "agent_input"},
        ),
        AIDDPlanStep(
            step_key="molecule_generation",
            tool_slug="gcdm-pocket-generation",
            depends_on=["pocket_prediction"],
            inputs={"pocket_pdb": "step:pocket_prediction:pocket_pdb"},
            params={"sample_num": 10},
        ),
    )
    step_contracts = {
        "pocket_prediction": _contract(
            tool_id="tool-pocket",
            slug="lvpocket-pocket-prediction",
            version_id="version-pocket",
            outputs=["pocket_pdb"],
        ),
        "molecule_generation": _contract(
            tool_id="tool-generation",
            slug="gcdm-pocket-generation",
            version_id="version-generation",
            outputs=["generated_ligand"],
        ),
    }

    first = build_workflow_definition_from_plan(
        plan=plan,
        input_files={"protein_pdb": "file-protein"},
        step_contracts=step_contracts,
    )
    second = build_workflow_definition_from_plan(
        plan=plan,
        input_files={"protein_pdb": "file-protein"},
        step_contracts=step_contracts,
    )

    assert first == second
    assert first["nodes"] == [
        {
            "id": "input-protein_pdb",
            "kind": "input",
            "semantic_type": "protein_pdb",
            "position": {"x": 40, "y": 120},
        },
        {
            "id": "pocket_prediction",
            "kind": "tool",
            "tool_id": "tool-pocket",
            "tool_slug": "lvpocket-pocket-prediction",
            "tool_version": {
                "id": "version-pocket",
                "version": "1.0.0",
                "is_active": True,
                "deprecated": False,
            },
            "semantic_inputs": {"protein_pdb": "workflow_input:protein_pdb"},
            "semantic_outputs": ["pocket_pdb"],
            "params": {},
            "position": {"x": 360, "y": 120},
        },
        {
            "id": "molecule_generation",
            "kind": "tool",
            "tool_id": "tool-generation",
            "tool_slug": "gcdm-pocket-generation",
            "tool_version": {
                "id": "version-generation",
                "version": "1.0.0",
                "is_active": True,
                "deprecated": False,
            },
            "semantic_inputs": {"pocket_pdb": "node:pocket_prediction:pocket_pdb"},
            "semantic_outputs": ["generated_ligand"],
            "params": {"sample_num": 10},
            "position": {"x": 680, "y": 120},
        },
    ]
    assert first["edges"] == [
        {
            "id": "edge-input-protein_pdb-pocket_prediction-protein_pdb",
            "source": "input-protein_pdb",
            "target": "pocket_prediction",
            "source_output": "protein_pdb",
            "target_input": "protein_pdb",
        },
        {
            "id": "edge-pocket_prediction-molecule_generation-pocket_pdb",
            "source": "pocket_prediction",
            "target": "molecule_generation",
            "source_output": "pocket_pdb",
            "target_input": "pocket_pdb",
        },
    ]


def test_build_workflow_definition_from_plan_preserves_standard_artifact_slots() -> None:
    plan = _plan(
        AIDDPlanStep(
            step_key="pocket_prediction",
            tool_slug="standard-pocket-tool",
            depends_on=[],
            inputs={"protein": "agent_input:protein_structure@1"},
        ),
        AIDDPlanStep(
            step_key="molecule_generation",
            tool_slug="standard-generation-tool",
            depends_on=["pocket_prediction"],
            inputs={"pocket": "step:pocket_prediction:pocket"},
        ),
    )

    definition = build_workflow_definition_from_plan(
        plan=plan,
        input_files={"protein_structure@1": "artifact-version-protein"},
        step_contracts={
            "pocket_prediction": _standard_contract(
                tool_id="tool-pocket",
                slug="standard-pocket-tool",
                version_id="version-pocket",
                inputs=[{"name": "protein", "type": "protein_structure@1", "required": True}],
                outputs=[
                    {
                        "name": "pocket",
                        "type": "binding_pocket@1",
                        "cardinality": "one",
                        "required": True,
                    }
                ],
            ),
            "molecule_generation": _standard_contract(
                tool_id="tool-generation",
                slug="standard-generation-tool",
                version_id="version-generation",
                inputs=[{"name": "pocket", "type": "binding_pocket@1", "required": True}],
                outputs=[
                    {
                        "name": "ligands",
                        "type": "ligand_structure@1",
                        "cardinality": "many",
                        "required": True,
                    }
                ],
            ),
        },
    )

    pocket_node = next(node for node in definition["nodes"] if node["id"] == "pocket_prediction")
    generation_node = next(node for node in definition["nodes"] if node["id"] == "molecule_generation")

    assert pocket_node["artifact_input_slots"] == [
        {"name": "protein", "type": "protein_structure@1", "required": True}
    ]
    assert pocket_node["artifact_inputs"] == {"protein": "workflow_input:protein_structure@1"}
    assert pocket_node["artifact_outputs"][0]["name"] == "pocket"
    assert generation_node["artifact_inputs"] == {"pocket": "node:pocket_prediction:pocket"}
    assert generation_node["artifact_outputs"][0]["type"] == "ligand_structure@1"


def test_build_workflow_definition_from_plan_rejects_unknown_input_source() -> None:
    plan = _plan(
        AIDDPlanStep(
            step_key="generation",
            tool_slug="gcdm-pocket-generation",
            depends_on=[],
            inputs={"pocket_pdb": "external:pocket"},
        )
    )

    with pytest.raises(ValidationException, match="Unsupported AIDD workflow draft input source"):
        build_workflow_definition_from_plan(
            plan=plan,
            input_files={"pocket_pdb": "file-pocket"},
            step_contracts={
                "generation": _contract(
                    tool_id="tool-generation",
                    slug="gcdm-pocket-generation",
                    version_id="version-generation",
                    outputs=["generated_ligand"],
                )
            },
        )
