"""LangGraph orchestration entrypoints for AIDD agent planning."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.aidd.graph_nodes import (
    classify_input_node,
    discover_tools_node,
    execute_step_node,
    load_context_node,
    observe_result_node,
    plan_steps_node,
    replan_or_finish_node,
    validate_plan_node,
)
from app.agents.aidd.graph_state import AIDDGraphState
from app.agents.aidd.planner import AIDDPlan, AIDDPlanStep
from app.agents.aidd.registry import load_available_tool_summaries
from app.common.exceptions import ValidationException
from app.models.files import File as FileModel
from app.services.model_services import get_default_model_service
from app.services.semantic_types import normalize_semantic_type


def build_aidd_graph():
    from langgraph.graph import END, START, StateGraph

    workflow = StateGraph(AIDDGraphState)
    workflow.add_node("load_context", load_context_node)
    workflow.add_node("classify_input", classify_input_node)
    workflow.add_node("discover_tools", discover_tools_node)
    workflow.add_node("plan_steps", plan_steps_node)
    workflow.add_node("validate_plan", validate_plan_node)
    workflow.add_node("execute_step", execute_step_node)
    workflow.add_node("observe_result", observe_result_node)
    workflow.add_node("replan_or_finish", replan_or_finish_node)

    workflow.add_edge(START, "load_context")
    workflow.add_edge("load_context", "classify_input")
    workflow.add_edge("classify_input", "discover_tools")
    workflow.add_edge("discover_tools", "plan_steps")
    workflow.add_edge("plan_steps", "validate_plan")
    workflow.add_edge("validate_plan", "execute_step")
    workflow.add_edge("execute_step", "observe_result")
    workflow.add_edge("observe_result", "replan_or_finish")
    workflow.add_edge("replan_or_finish", END)
    return workflow.compile()


def _plan_dict_to_aidd_plan(plan_data: dict, requested_outputs: list[str]) -> AIDDPlan:
    return AIDDPlan(
        intent=plan_data["intent"],
        requested_outputs=requested_outputs or ["generated_ligand"],
        reasoning_summary=plan_data.get("reasoning_summary"),
        analysis_trace=plan_data.get("analysis_trace") or [],
        steps=[
            AIDDPlanStep(
                step_key=step["step_key"],
                tool_slug=step["tool_slug"],
                depends_on=step.get("depends_on", []),
                inputs=step.get("inputs", {}),
                params=step.get("params", {}),
            )
            for step in plan_data.get("steps", [])
        ],
    )


async def build_plan_with_langgraph(
    db: AsyncSession,
    *,
    message: str,
    input_file: FileModel,
    input_files: dict[str, FileModel] | None = None,
    input_type: str | None = None,
    requested_outputs: list[str],
    params: dict,
) -> tuple[AIDDPlan, str]:
    model_service = await get_default_model_service(db)
    graph = build_aidd_graph()
    semantic_input_payload = {
        normalize_semantic_type(semantic_type): {
            "source": "agent_input",
            "file_id": file_record.id,
            "filename": file_record.filename,
        }
        for semantic_type, file_record in (input_files or {}).items()
    }

    state: AIDDGraphState = {
        "message": message,
        "input_file_id": input_file.id,
        "input_filename": input_file.filename,
        "input_files": semantic_input_payload,
        "input_type": normalize_semantic_type(input_type) if input_type else input_type,
        "requested_outputs": [normalize_semantic_type(output) for output in requested_outputs],
        "params": params,
        "configured_tools": await load_available_tool_summaries(db),
        "model_service": model_service,
    }

    try:
        result = await graph.ainvoke(state)
    except Exception as exc:
        raise ValidationException(f"智能体规划失败: {exc}") from exc

    plan_data = result.get("plan")
    if not plan_data:
        raise ValidationException("智能体规划未生成可执行计划")

    return _plan_dict_to_aidd_plan(plan_data, requested_outputs), str(result.get("input_type"))
