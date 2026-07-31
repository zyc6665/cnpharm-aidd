"""LangGraph node functions for AIDD planning only.

Task creation, execution, observation, and replanning are handled by the
agent service after this graph returns a validated plan.
"""

from __future__ import annotations

from typing import Any

from app.agents.aidd.capabilities import AIDD_TOOL_CAPABILITIES
from app.agents.aidd.graph_state import AIDDGraphState
from app.agents.aidd.plan_schema import (
    build_planning_prompt,
    parse_model_plan,
)
from app.agents.aidd.planner import infer_aidd_input_type
from app.agents.aidd.registry import capability_to_tool_summary


def _capability_to_tool_summary(tool_slug: str) -> dict[str, Any]:
    capability = AIDD_TOOL_CAPABILITIES[tool_slug]
    return capability_to_tool_summary(capability)


def load_context_node(state: AIDDGraphState) -> AIDDGraphState:
    return {"status": "context_loaded"}


def build_project_lvpocket_plan_node(state: AIDDGraphState) -> AIDDGraphState:
    """Build the production-validated first vertical without side effects."""
    protein_version_id = state.get("protein_artifact_version_id")
    if not protein_version_id:
        return {"status": "input_required"}
    return {
        "plan": {
            "goal": state.get("message", ""),
            "protein_artifact_version_id": protein_version_id,
            "intent": "pocket_detection",
            "reasoning_summary": "使用已验证的 LVpocket NVIDIA 变体识别候选结合口袋。",
            "requested_outputs": ["pocket_pdb", "pocket_report"],
            "parameters": {},
            "steps": [
                {
                    "step_key": "pocket_prediction",
                    "tool_slug": "lvpocket-pocket-prediction",
                    "inputs": {"protein_pdb": protein_version_id},
                    "outputs": ["pocket_pdb", "pocket_report"],
                    "parameters": {},
                }
            ],
        },
        "reasoning_summary": "使用已验证的 LVpocket NVIDIA 变体识别候选结合口袋。",
        "status": "planned",
    }


def classify_input_node(state: AIDDGraphState) -> AIDDGraphState:
    if state.get("input_files"):
        semantic_inputs = state["input_files"]
        input_type = state.get("input_type") or next(iter(semantic_inputs.keys()))
        return {
            "input_type": input_type,
            "semantic_inputs": semantic_inputs,
            "status": "input_classified",
        }

    input_type = infer_aidd_input_type(
        message=state.get("message", ""),
        filename=state.get("input_filename", ""),
    )
    return {
        "input_type": input_type,
        "semantic_inputs": {
            input_type: {
                "source": "agent_input",
                "file_id": state.get("input_file_id"),
                "filename": state.get("input_filename"),
            }
        },
        "status": "input_classified",
    }


def discover_tools_node(state: AIDDGraphState) -> AIDDGraphState:
    if "configured_tools" in state:
        return {
            "available_tools": state.get("configured_tools") or [],
            "status": "tools_discovered",
        }

    configured_slugs = set(
        state.get("configured_tool_slugs") or AIDD_TOOL_CAPABILITIES.keys()
    )
    available_tools = [
        _capability_to_tool_summary(tool_slug)
        for tool_slug, capability in AIDD_TOOL_CAPABILITIES.items()
        if capability.virtual or tool_slug in configured_slugs
    ]
    return {
        "available_tools": available_tools,
        "status": "tools_discovered",
    }


async def plan_steps_node(state: AIDDGraphState) -> AIDDGraphState:
    from app.agents.aidd.llm_client import request_structured_plan

    prompt = build_planning_prompt(
        message=state.get("message", ""),
        semantic_inputs=state.get("semantic_inputs", {}),
        available_tools=state.get("available_tools", []),
        requested_outputs=state.get("requested_outputs", []),
    )
    raw_plan = await request_structured_plan(state["model_service"], prompt)
    return {
        "planning_prompt": prompt,
        "raw_plan": raw_plan,
        "status": "plan_received",
    }


def validate_plan_node(state: AIDDGraphState) -> AIDDGraphState:
    plan = parse_model_plan(
        state.get("raw_plan", ""),
        available_tools=state.get("available_tools", []),
        available_input_types=set((state.get("semantic_inputs") or {}).keys()),
    )
    return {
        "plan": plan.model_dump(),
        "reasoning_summary": plan.reasoning_summary,
        "analysis_trace": plan.analysis_trace,
        "status": "planned",
    }
