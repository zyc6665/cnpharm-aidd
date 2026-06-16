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


SDF_TO_SMILES_TOOL_SLUG = "builtin-sdf-to-smiles-csv"


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
            "如果性质预测需要 smiles_csv，而分子生成只产生 generated_ligand SDF，必须插入 builtin-sdf-to-smiles-csv 格式转换步骤。",
            "如果亲和力预测需要 ligand_pdb，而分子生成或上传文件只提供 generated_ligand SDF，必须先插入 builtin-sdf-to-pdb 格式转换步骤。",
            "如果用户要求 Vina、docking、对接或排序评估，应使用 builtin-vina-docking 生成 docking_report 和 ranking_csv；如果只有 generated_ligand SDF，先转 ligand_pdb。",
            "如果用户同时上传 protein_pdb 和 ligand_pdb，亲和力预测应直接使用 agent_input:protein_pdb 与 agent_input:ligand_pdb。",
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


def _normalize_input_sources(inputs: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for semantic_input, source in inputs.items():
        if isinstance(source, str) and source.startswith("agent_input:"):
            normalized[semantic_input] = "agent_input"
            continue
        normalized[semantic_input] = source
    return normalized


def _tool_outputs(tool: dict[str, Any] | None) -> set[str]:
    if not tool:
        return set()
    return {str(output) for output in tool.get("outputs", [])}


def _unique_step_key(base: str, used_step_keys: set[str]) -> str:
    if base not in used_step_keys:
        return base

    suffix = 2
    while f"{base}_{suffix}" in used_step_keys:
        suffix += 1
    return f"{base}_{suffix}"


def _is_step_smiles_source(source: str) -> tuple[str, str] | None:
    if not isinstance(source, str) or not source.startswith("step:"):
        return None
    parts = source.split(":", 2)
    if len(parts) != 3:
        return None
    return parts[1], parts[2]


def _repair_generated_ligand_smiles_sources(
    plan: AIDDGraphPlan,
    *,
    tools_by_slug: dict[str, dict[str, Any]],
) -> AIDDGraphPlan:
    """Insert SDF->SMILES conversion when a generated SDF is used as smiles_csv."""
    if SDF_TO_SMILES_TOOL_SLUG not in tools_by_slug:
        return plan

    original_steps_by_key = {step.step_key: step for step in plan.steps}
    used_step_keys = set(original_steps_by_key)
    emitted_step_keys: set[str] = set()
    converter_step_by_source: dict[str, str] = {}
    repaired_steps: list[AIDDGraphPlanStep] = []

    for step in plan.steps:
        if step.tool_slug == SDF_TO_SMILES_TOOL_SLUG:
            source = step.inputs.get("generated_ligand")
            parsed_source = _is_step_smiles_source(source) if source else None
            if parsed_source:
                converter_step_by_source[parsed_source[0]] = step.step_key
            repaired_steps.append(step)
            emitted_step_keys.add(step.step_key)
            continue

        repaired_inputs = dict(step.inputs)
        replaced_source_steps: set[str] = set()

        for semantic_input, source in list(step.inputs.items()):
            if semantic_input != "smiles_csv":
                continue

            parsed_source = _is_step_smiles_source(source)
            if parsed_source is None:
                continue

            source_step_key, source_output = parsed_source
            if source_output != "smiles_csv" or source_step_key not in emitted_step_keys:
                continue

            source_step = original_steps_by_key.get(source_step_key)
            source_tool = tools_by_slug.get(source_step.tool_slug if source_step else "")
            if "generated_ligand" not in _tool_outputs(source_tool):
                continue

            converter_step_key = converter_step_by_source.get(source_step_key)
            if converter_step_key is None:
                converter_step_key = _unique_step_key("sdf_to_smiles", used_step_keys)
                used_step_keys.add(converter_step_key)
                converter_step_by_source[source_step_key] = converter_step_key
                repaired_steps.append(
                    AIDDGraphPlanStep(
                        step_key=converter_step_key,
                        capability="format_conversion",
                        tool_slug=SDF_TO_SMILES_TOOL_SLUG,
                        inputs={
                            "generated_ligand": (
                                f"step:{source_step_key}:generated_ligand"
                            )
                        },
                        params={},
                        depends_on=[source_step_key],
                    )
                )
                emitted_step_keys.add(converter_step_key)

            repaired_inputs[semantic_input] = f"step:{converter_step_key}:smiles_csv"
            replaced_source_steps.add(source_step_key)

        if replaced_source_steps:
            normalized_inputs = _normalize_input_sources(repaired_inputs)
            derived_depends_on = _derive_depends_on(normalized_inputs)
            depends_on = [
                dependency
                for dependency in step.depends_on
                if dependency not in replaced_source_steps
            ]
            for dependency in derived_depends_on:
                if dependency not in depends_on:
                    depends_on.append(dependency)
            step = step.model_copy(
                update={"inputs": repaired_inputs, "depends_on": depends_on}
            )

        repaired_steps.append(step)
        emitted_step_keys.add(step.step_key)

    return plan.model_copy(update={"steps": repaired_steps})


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
    plan = _repair_generated_ligand_smiles_sources(plan, tools_by_slug=tools_by_slug)
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

        normalized_inputs = _normalize_input_sources(step.inputs)
        depends_on = step.depends_on or _derive_depends_on(normalized_inputs)
        for dependency_key in depends_on:
            if dependency_key not in seen_step_keys:
                raise PlanValidationError(f"依赖步骤不存在或顺序错误: {dependency_key}")

        normalized_steps.append(
            step.model_copy(update={"inputs": normalized_inputs, "depends_on": depends_on})
        )

    return plan.model_copy(update={"steps": normalized_steps})
