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
    {
        "tool_slug": "builtin-sdf-to-smiles-csv",
        "capability": "format_conversion",
        "inputs": ["generated_ligand"],
        "outputs": ["smiles_csv"],
    },
    {
        "tool_slug": "molp-pc-property-prediction",
        "capability": "property_prediction",
        "inputs": ["smiles_csv"],
        "outputs": ["property_report"],
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


def test_parse_model_plan_accepts_standard_artifact_slots():
    standard_tools = [
        {
            "tool_slug": "standard-pocket-tool",
            "capability": "standard-pocket-tool",
            "artifact_inputs": [
                {"name": "protein", "type": "protein_structure@1", "required": True}
            ],
            "artifact_outputs": [
                {
                    "name": "pocket",
                    "type": "binding_pocket@1",
                    "cardinality": "one",
                    "required": True,
                }
            ],
            "inputs": ["protein_structure@1"],
            "outputs": ["binding_pocket@1"],
        }
    ]

    plan = parse_model_plan(
        """
        {
          "intent": "standard_pocket_prediction",
          "steps": [
            {
              "step_key": "pocket_prediction",
              "capability": "standard-pocket-tool",
              "tool_slug": "standard-pocket-tool",
              "inputs": {"protein": "agent_input:protein_structure@1"},
              "params": {}
            }
          ]
        }
        """,
        available_tools=standard_tools,
        available_input_types={"protein_structure@1"},
    )

    assert plan.steps[0].inputs == {"protein": "agent_input"}


def test_parse_model_plan_rejects_missing_standard_artifact_input_type():
    with pytest.raises(PlanValidationError, match="未上传输入"):
        parse_model_plan(
            """
            {
              "intent": "standard_pocket_prediction",
              "steps": [
                {
                  "step_key": "pocket_prediction",
                  "capability": "standard-pocket-tool",
                  "tool_slug": "standard-pocket-tool",
                  "inputs": {"protein": "agent_input:protein_structure@1"},
                  "params": {}
                }
              ]
            }
            """,
            available_tools=[
                {
                    "tool_slug": "standard-pocket-tool",
                    "capability": "standard-pocket-tool",
                    "artifact_inputs": [
                        {"name": "protein", "type": "protein_structure@1", "required": True}
                    ],
                    "artifact_outputs": [
                        {"name": "pocket", "type": "binding_pocket@1", "required": True}
                    ],
                }
            ],
            available_input_types=set(),
        )


def test_parse_model_plan_repairs_generated_ligand_smiles_csv_reference():
    plan = parse_model_plan(
        """
        {
          "intent": "score_generated_molecules",
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
            },
            {
              "step_key": "property_prediction",
              "capability": "property_prediction",
              "tool_slug": "molp-pc-property-prediction",
              "inputs": {"smiles_csv": "step:molecule_generation:smiles_csv"},
              "params": {}
            }
          ]
        }
        """,
        available_tools=AVAILABLE_TOOLS,
    )

    assert [step.step_key for step in plan.steps] == [
        "pocket_prediction",
        "molecule_generation",
        "sdf_to_smiles",
        "property_prediction",
    ]
    conversion_step = plan.steps[2]
    assert conversion_step.tool_slug == "builtin-sdf-to-smiles-csv"
    assert conversion_step.capability == "format_conversion"
    assert conversion_step.inputs == {
        "generated_ligand": "step:molecule_generation:generated_ligand"
    }
    assert conversion_step.depends_on == ["molecule_generation"]
    assert plan.steps[3].inputs == {"smiles_csv": "step:sdf_to_smiles:smiles_csv"}
    assert plan.steps[3].depends_on == ["sdf_to_smiles"]


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


def test_parse_model_plan_rejects_missing_upstream_semantic_output():
    with pytest.raises(PlanValidationError, match="不产生语义产物"):
        parse_model_plan(
            """
            {
              "intent": "bad_reference",
              "steps": [
                {
                  "step_key": "pocket_prediction",
                  "capability": "pocket_prediction",
                  "tool_slug": "lvpocket-pocket-prediction",
                  "inputs": {"protein_pdb": "agent_input"}
                },
                {
                  "step_key": "molecule_generation",
                  "capability": "molecule_generation",
                  "tool_slug": "gcdm-pocket-generation",
                  "inputs": {"pocket_pdb": "step:pocket_prediction:missing_output"}
                }
              ]
            }
            """,
            available_tools=AVAILABLE_TOOLS,
        )


def test_parse_model_plan_rejects_non_json():
    with pytest.raises(PlanValidationError):
        parse_model_plan("not a json plan", available_tools=AVAILABLE_TOOLS)
