"""Structured AIDD plan schema and validation."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field


class PlanValidationError(ValueError):
    """Raised when an LLM plan is not executable by the platform."""


class AIDDGraphPlanStep(BaseModel):
    step_key: str
    capability: str
    tool_slug: str
    inputs: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class AIDDGraphPlan(BaseModel):
    intent: str
    reasoning_summary: str | None = None
    analysis_trace: list[str] = Field(default_factory=list)
    steps: list[AIDDGraphPlanStep]
    finish_condition: str | None = None


def _strip_json_fence(content: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)```", content, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return content.strip()


def build_planning_prompt(
    *,
    message: str,
    semantic_inputs: dict[str, dict[str, Any]],
    available_tools: list[dict[str, Any]],
    requested_outputs: list[str],
) -> str:
    return "\n".join(
        [
            "你是 CPUModel AIDD 工具编排智能体。",
            "根据用户目标、已上传文件语义和可用工具，生成可执行的结构化计划。",
            "只返回 JSON，不要返回 Markdown。",
            "reasoning_summary 只写面向用户的简短规划说明，不要输出逐步隐藏推理。",
            "analysis_trace 写 3-6 条面向用户的分析过程，覆盖输入判断、工具发现、工具选择、依赖编排和参数依据；不要输出原始隐藏推理链。",
            "",
            f"用户目标: {message}",
            f"已知输入语义: {json.dumps(semantic_inputs, ensure_ascii=False)}",
            f"期望输出: {json.dumps(requested_outputs, ensure_ascii=False)}",
            f"可用工具: {json.dumps(available_tools, ensure_ascii=False)}",
            "",
            "JSON schema:",
            json.dumps(
                {
                    "intent": "short_intent_name",
                    "reasoning_summary": "brief user-facing planning rationale without hidden chain-of-thought",
                    "analysis_trace": [
                        "user-visible input classification",
                        "user-visible tool discovery and selection rationale",
                        "user-visible orchestration and parameter rationale",
                    ],
                    "steps": [
                        {
                            "step_key": "unique_step_key",
                            "capability": "registered_capability",
                            "tool_slug": "available_tool_slug",
                            "inputs": {"semantic_input": "agent_input or step:step_key:semantic_output"},
                            "params": {},
                        }
                    ],
                    "finish_condition": "optional_finish_condition",
                },
                ensure_ascii=False,
            ),
        ]
    )


def _derive_depends_on(inputs: dict[str, str]) -> list[str]:
    depends_on: list[str] = []
    for source in inputs.values():
        if isinstance(source, str) and source.startswith("step:"):
            parts = source.split(":", 2)
            if len(parts) >= 2 and parts[1] not in depends_on:
                depends_on.append(parts[1])
    return depends_on


def parse_model_plan(
    content: str,
    *,
    available_tools: list[dict[str, Any]],
) -> AIDDGraphPlan:
    try:
        raw = json.loads(_strip_json_fence(content))
        plan = AIDDGraphPlan.model_validate(raw)
    except Exception as exc:
        raise PlanValidationError(f"模型计划不是有效 JSON: {exc}") from exc

    if not plan.steps:
        raise PlanValidationError("模型计划至少需要一个步骤")

    tools_by_slug = {tool["tool_slug"]: tool for tool in available_tools}
    seen_step_keys: set[str] = set()
    normalized_steps: list[AIDDGraphPlanStep] = []

    for step in plan.steps:
        if step.step_key in seen_step_keys:
            raise PlanValidationError(f"步骤 key 重复: {step.step_key}")
        seen_step_keys.add(step.step_key)

        tool = tools_by_slug.get(step.tool_slug)
        if not tool:
            raise PlanValidationError(f"计划使用了不可用工具: {step.tool_slug}")
        if tool.get("capability") != step.capability:
            raise PlanValidationError(f"工具能力不匹配: {step.tool_slug}")

        depends_on = step.depends_on or _derive_depends_on(step.inputs)
        for dependency_key in depends_on:
            if dependency_key not in seen_step_keys:
                raise PlanValidationError(f"依赖步骤不存在或顺序错误: {dependency_key}")

        normalized_steps.append(step.model_copy(update={"depends_on": depends_on}))

    return plan.model_copy(update={"steps": normalized_steps})
