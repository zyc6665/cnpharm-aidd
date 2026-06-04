"""AIDD agent plan builder tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.planner import build_aidd_plan  # noqa: E402


def test_protein_input_builds_pocket_then_generation_plan() -> None:
    plan = build_aidd_plan(
        message="上传蛋白后进行口袋探索并生成分子",
        input_type="protein_pdb",
        requested_outputs=["generated_ligand"],
        params={"generation_count": 12},
    )

    assert plan.intent == "generate_molecules_from_protein"
    assert [step.tool_slug for step in plan.steps] == [
        "lvpocket-pocket-prediction",
        "gcdm-pocket-generation",
    ]
    assert plan.steps[1].depends_on == ["pocket_prediction"]
    assert plan.steps[1].params["params.n_samples"] == 12


def test_pocket_input_skips_lvpocket() -> None:
    plan = build_aidd_plan(
        message="基于这个口袋生成分子",
        input_type="pocket_pdb",
        requested_outputs=["generated_ligand"],
        params={},
    )

    assert plan.intent == "generate_molecules_from_pocket"
    assert [step.tool_slug for step in plan.steps] == ["gcdm-pocket-generation"]


def test_property_prediction_can_be_appended_when_requested() -> None:
    plan = build_aidd_plan(
        message="从蛋白生成分子并预测性质",
        input_type="protein_pdb",
        requested_outputs=["generated_ligand", "property_report"],
        params={},
    )

    assert [step.step_key for step in plan.steps] == [
        "pocket_prediction",
        "molecule_generation",
        "property_prediction",
    ]
    assert plan.steps[2].depends_on == ["molecule_generation"]
