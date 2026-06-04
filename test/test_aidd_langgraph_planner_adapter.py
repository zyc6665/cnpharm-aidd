import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.plan_schema import (
    PlanValidationError,
    build_planning_prompt,
    parse_model_plan,
)


AVAILABLE_TOOLS = [
    {
        "tool_slug": "lvpocket-pocket-prediction",
        "capability": "pocket_prediction",
        "inputs": ["protein_pdb"],
        "outputs": ["pocket_pdb"],
    },
    {
        "tool_slug": "gcdm-pocket-generation",
        "capability": "molecule_generation",
        "inputs": ["pocket_pdb"],
        "outputs": ["generated_ligand"],
    },
]


def test_build_planning_prompt_contains_goal_inputs_and_tools():
    prompt = build_planning_prompt(
        message="上传蛋白后探索口袋并生成分子",
        semantic_inputs={"protein_pdb": {"file_id": "file-1", "filename": "protein.pdb"}},
        available_tools=AVAILABLE_TOOLS,
        requested_outputs=["generated_ligand"],
    )

    assert "上传蛋白后探索口袋并生成分子" in prompt
    assert "protein_pdb" in prompt
    assert "lvpocket-pocket-prediction" in prompt
    assert "只返回 JSON" in prompt
    assert "reasoning_summary" in prompt
    assert "analysis_trace" in prompt
    assert "隐藏推理" in prompt


def test_parse_model_plan_accepts_valid_json_plan():
    plan = parse_model_plan(
        """
        {
          "intent": "generate_molecules_from_protein",
          "reasoning_summary": "识别到蛋白结构输入，先预测口袋，再把口袋结构交给分子生成工具。",
          "analysis_trace": [
            "输入判断：上传文件是蛋白结构，入口语义为 protein_pdb。",
            "工具选择：需要先用口袋预测能力生成 pocket_pdb。",
            "编排结果：将口袋预测产物传给分子生成能力。"
          ],
          "steps": [
            {
              "step_key": "pocket_prediction",
              "capability": "pocket_prediction",
              "tool_slug": "lvpocket-pocket-prediction",
              "inputs": {"protein_pdb": "agent_input"},
              "params": {}
            },
            {
              "step_key": "molecule_generation",
              "capability": "molecule_generation",
              "tool_slug": "gcdm-pocket-generation",
              "inputs": {"pocket_pdb": "step:pocket_prediction:pocket_pdb"},
              "params": {}
            }
          ],
          "finish_condition": "generated_ligand_ready"
        }
        """,
        available_tools=AVAILABLE_TOOLS,
    )

    assert plan.intent == "generate_molecules_from_protein"
    assert plan.reasoning_summary == "识别到蛋白结构输入，先预测口袋，再把口袋结构交给分子生成工具。"
    assert plan.analysis_trace == [
        "输入判断：上传文件是蛋白结构，入口语义为 protein_pdb。",
        "工具选择：需要先用口袋预测能力生成 pocket_pdb。",
        "编排结果：将口袋预测产物传给分子生成能力。",
    ]
    assert [step.tool_slug for step in plan.steps] == [
        "lvpocket-pocket-prediction",
        "gcdm-pocket-generation",
    ]
    assert plan.steps[1].depends_on == ["pocket_prediction"]


def test_parse_model_plan_rejects_unknown_tool():
    with pytest.raises(PlanValidationError):
        parse_model_plan(
            """
            {
              "intent": "bad",
              "steps": [
                {
                  "step_key": "bad",
                  "capability": "molecule_generation",
                  "tool_slug": "unknown-tool",
                  "inputs": {},
                  "params": {}
                }
              ]
            }
            """,
            available_tools=AVAILABLE_TOOLS,
        )


def test_parse_model_plan_rejects_non_json():
    with pytest.raises(PlanValidationError):
        parse_model_plan("not a json plan", available_tools=AVAILABLE_TOOLS)
