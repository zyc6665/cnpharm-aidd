"""Convert validated AIDD plans into editable workflow definitions."""

from __future__ import annotations

from typing import Any

from app.agents.aidd.planner import AIDDPlan
from app.common.exceptions import ValidationException
from app.artifact_standards.registry import is_standard_artifact_ref
from app.services.semantic_types import normalize_semantic_type
from app.services.workflow_validation import validate_workflow_definition


_INPUT_X = 40
_TOOL_X = 360
_COLUMN_GAP = 320
_ROW_Y = 120
_ROW_GAP = 160


def build_workflow_definition_from_plan(
    *,
    plan: AIDDPlan,
    input_files: dict[str, str],
    step_contracts: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Build a runnable workflow definition without persisting workflow state."""
    normalized_input_files = {
        _normalize_type_identifier(semantic_type): str(file_id)
        for semantic_type, file_id in input_files.items()
        if file_id
    }
    step_keys = {step.step_key for step in plan.steps}
    if len(step_keys) != len(plan.steps):
        raise ValidationException("AIDD workflow draft step keys must be unique")

    semantic_inputs_by_step: dict[str, dict[str, str]] = {}
    input_types: set[str] = set()
    edges: list[dict[str, Any]] = []

    artifact_inputs_by_step: dict[str, dict[str, str]] = {}

    for step in plan.steps:
        contract = step_contracts.get(step.step_key) or {}
        artifact_input_slots = _contract_artifact_input_slots(contract)
        artifact_slot_types = {str(item["name"]): str(item["type"]) for item in artifact_input_slots}
        semantic_inputs: dict[str, str] = {}
        artifact_inputs: dict[str, str] = {}
        for semantic_input, raw_source in step.inputs.items():
            is_artifact_slot = semantic_input in artifact_slot_types
            target_type = semantic_input if is_artifact_slot else normalize_semantic_type(semantic_input)
            source = str(raw_source)
            if source == "agent_input" or source.startswith("agent_input:"):
                source_type = artifact_slot_types.get(semantic_input, target_type)
                if source.startswith("agent_input:"):
                    source_type = _normalize_type_identifier(source.split(":", 1)[1] or source_type)
                if source_type not in normalized_input_files:
                    raise ValidationException(
                        f"AIDD workflow draft is missing input file: {source_type}"
                    )
                input_types.add(source_type)
                source_ref = f"workflow_input:{source_type}"
                if is_artifact_slot:
                    artifact_inputs[target_type] = source_ref
                else:
                    semantic_inputs[target_type] = source_ref
                edges.append(
                    _edge(
                        source=f"input-{source_type}",
                        target=step.step_key,
                        source_output=source_type,
                        target_input=target_type,
                    )
                )
                continue

            if source.startswith("step:"):
                parts = source.split(":", 2)
                if len(parts) != 3 or parts[1] not in step_keys or not parts[2]:
                    raise ValidationException(
                        f"Invalid AIDD workflow draft step input source: {source}"
                    )
                source_step = parts[1]
                source_output = parts[2] if is_artifact_slot else normalize_semantic_type(parts[2])
                source_ref = f"node:{source_step}:{source_output}"
                if is_artifact_slot:
                    artifact_inputs[target_type] = source_ref
                else:
                    semantic_inputs[target_type] = source_ref
                edges.append(
                    _edge(
                        source=source_step,
                        target=step.step_key,
                        source_output=source_output,
                        target_input=target_type,
                    )
                )
                continue

            raise ValidationException(
                f"Unsupported AIDD workflow draft input source: {source}"
            )
        semantic_inputs_by_step[step.step_key] = semantic_inputs
        artifact_inputs_by_step[step.step_key] = artifact_inputs

    depths = _step_depths(plan)
    rows_by_depth: dict[int, int] = {}
    nodes: list[dict[str, Any]] = [
        {
            "id": f"input-{semantic_type}",
            "kind": "input",
            "semantic_type": semantic_type,
            "position": {"x": _INPUT_X, "y": _ROW_Y + index * _ROW_GAP},
        }
        for index, semantic_type in enumerate(sorted(input_types))
    ]

    for step in plan.steps:
        contract = step_contracts.get(step.step_key)
        if not contract or not contract.get("id") or not contract.get("tool_version"):
            raise ValidationException(
                f"AIDD workflow draft tool is not executable: {step.tool_slug}"
            )
        depth = depths[step.step_key]
        row = rows_by_depth.get(depth, 0)
        rows_by_depth[depth] = row + 1
        node = {
            "id": step.step_key,
            "kind": "tool",
            "tool_id": str(contract["id"]),
            "tool_slug": step.tool_slug,
            "tool_version": dict(contract["tool_version"]),
            "semantic_inputs": semantic_inputs_by_step[step.step_key],
            "semantic_outputs": _contract_output_types(contract),
            "params": dict(step.params or {}),
            "position": {
                "x": _TOOL_X + (depth - 1) * _COLUMN_GAP,
                "y": _ROW_Y + row * _ROW_GAP,
            },
        }
        artifact_input_slots = _contract_artifact_input_slots(contract)
        artifact_outputs = _contract_artifact_output_slots(contract)
        if artifact_input_slots:
            node["artifact_input_slots"] = artifact_input_slots
            node["artifact_inputs"] = artifact_inputs_by_step[step.step_key]
        if artifact_outputs:
            node["artifact_outputs"] = artifact_outputs
        nodes.append(node)

    definition = {"nodes": nodes, "edges": edges}
    validate_workflow_definition(definition)
    return definition


def _normalize_type_identifier(value: str) -> str:
    raw = str(value)
    return raw if is_standard_artifact_ref(raw) else normalize_semantic_type(raw)


def _contract_artifact_input_slots(contract: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": str(item["name"]),
            "type": str(item["type"]),
            "required": bool(item.get("required", True)),
        }
        for item in contract.get("artifact_inputs", [])
        if isinstance(item, dict) and item.get("name") and item.get("type")
    ]


def _contract_artifact_output_slots(contract: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": str(item["name"]),
            "type": str(item["type"]),
            "cardinality": str(item.get("cardinality") or "one"),
            "required": bool(item.get("required", True)),
        }
        for item in contract.get("artifact_outputs", [])
        if isinstance(item, dict) and item.get("name") and item.get("type")
    ]


def _step_depths(plan: AIDDPlan) -> dict[str, int]:
    dependencies = {
        step.step_key: {
            source.split(":", 2)[1]
            for source in step.inputs.values()
            if isinstance(source, str) and source.startswith("step:")
        }
        | set(step.depends_on or [])
        for step in plan.steps
    }
    depths: dict[str, int] = {}

    def resolve(step_key: str, visiting: set[str]) -> int:
        if step_key in depths:
            return depths[step_key]
        if step_key in visiting:
            raise ValidationException("AIDD workflow draft contains a cycle")
        if step_key not in dependencies:
            raise ValidationException(f"AIDD workflow draft references unknown step: {step_key}")
        visiting.add(step_key)
        sources = dependencies[step_key]
        depth = 1 if not sources else max(resolve(source, visiting) for source in sources) + 1
        visiting.remove(step_key)
        depths[step_key] = depth
        return depth

    for step_key in dependencies:
        resolve(step_key, set())
    return depths


def _contract_output_types(contract: dict[str, Any]) -> list[str]:
    return [
        normalize_semantic_type(str(rule["semantic_type"]))
        for rule in contract.get("output_rules", [])
        if isinstance(rule, dict) and rule.get("semantic_type")
    ]


def _edge(
    *,
    source: str,
    target: str,
    source_output: str,
    target_input: str,
) -> dict[str, str]:
    return {
        "id": f"edge-{source}-{target}-{target_input}",
        "source": source,
        "target": target,
        "source_output": source_output,
        "target_input": target_input,
    }
