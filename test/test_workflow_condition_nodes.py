"""Workflow condition node tests."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.workflow_conditions import evaluate_condition_expression  # noqa: E402
from app.services.workflow_dependencies import dependencies_satisfied  # noqa: E402
from app.services.workflow_validation import (
    is_condition_node,
    is_control_flow_node,
    is_loop_node,
    is_map_node,
    validate_workflow_definition,
    workflow_dependency_map,
)


class TestNodeTypeHelpers:
    def test_is_condition_node(self):
        assert is_condition_node({"id": "c1", "kind": "condition", "expression": {}})
        assert is_condition_node({"id": "c1", "type": "condition", "expression": {}})
        assert not is_condition_node({"id": "t1", "kind": "tool"})
        assert not is_condition_node(None)

    def test_is_map_node(self):
        assert is_map_node({"id": "m1", "kind": "map", "over": "workflow_input:x"})
        assert not is_map_node({"id": "t1", "kind": "tool"})

    def test_is_loop_node(self):
        assert is_loop_node({"id": "l1", "kind": "loop", "body": ["a"]})
        assert not is_loop_node({"id": "t1", "kind": "tool"})

    def test_is_control_flow_node(self):
        assert is_control_flow_node({"id": "c1", "kind": "condition", "expression": {}})
        assert is_control_flow_node({"id": "m1", "kind": "map", "over": "x"})
        assert is_control_flow_node({"id": "l1", "kind": "loop", "body": ["a"]})
        assert not is_control_flow_node({"id": "t1", "kind": "tool"})


class TestConditionValidation:
    def test_condition_without_expression_raises(self):
        definition = {
            "nodes": [
                {"id": "input", "kind": "input"},
                {"id": "cond", "kind": "condition"},
                {"id": "tool_a", "kind": "tool", "tool_slug": "a"},
            ],
            "edges": [
                {"source": "input", "target": "cond"},
                {"source": "cond", "target": "tool_a", "branch": "true"},
            ],
        }
        with pytest.raises(Exception) as exc_info:
            validate_workflow_definition(definition)
        assert "expression" in str(exc_info.value).lower()

    def test_condition_with_invalid_operator_raises(self):
        definition = {
            "nodes": [
                {"id": "input", "kind": "input"},
                {
                    "id": "cond",
                    "kind": "condition",
                    "expression": {"op": "+", "left": 1, "right": 2},
                },
                {"id": "tool_a", "kind": "tool", "tool_slug": "a"},
            ],
            "edges": [
                {"source": "input", "target": "cond"},
                {"source": "cond", "target": "tool_a", "branch": "true"},
            ],
        }
        with pytest.raises(Exception) as exc_info:
            validate_workflow_definition(definition)
        assert "unsupported operator" in str(exc_info.value).lower()

    def test_condition_in_execution_order(self):
        definition = {
            "nodes": [
                {"id": "input", "kind": "input"},
                {
                    "id": "cond",
                    "kind": "condition",
                    "expression": {"op": "==", "left": "a", "right": "b"},
                },
                {"id": "tool_a", "kind": "tool", "tool_slug": "a"},
                {"id": "tool_b", "kind": "tool", "tool_slug": "b"},
            ],
            "edges": [
                {"source": "input", "target": "cond"},
                {"source": "cond", "target": "tool_a", "branch": "true"},
                {"source": "cond", "target": "tool_b", "branch": "false"},
            ],
        }
        order = validate_workflow_definition(definition)
        assert "cond" in order
        assert "tool_a" in order
        assert "tool_b" in order

    def test_condition_branch_edges_not_in_dependency_map(self):
        definition = {
            "nodes": [
                {"id": "input", "kind": "input"},
                {
                    "id": "cond",
                    "kind": "condition",
                    "expression": {"op": "==", "left": "a", "right": "b"},
                },
                {"id": "tool_a", "kind": "tool", "tool_slug": "a"},
                {"id": "tool_b", "kind": "tool", "tool_slug": "b"},
            ],
            "edges": [
                {"source": "input", "target": "cond"},
                {"source": "cond", "target": "tool_a", "branch": "true"},
                {"source": "cond", "target": "tool_b", "branch": "false"},
            ],
        }
        deps = workflow_dependency_map(definition)
        # 两条分支 edge 不应出现在 tool_a/tool_b 的依赖中
        assert "tool_a" not in deps.get("cond", set())
        assert "tool_b" not in deps.get("cond", set())
        assert deps["tool_a"] == {"cond"} or deps["tool_a"] == set()
        assert deps["tool_b"] == {"cond"} or deps["tool_b"] == set()


class TestEvaluateConditionExpression:
    def test_equal_operator_with_literals(self):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun(input_files={})
        assert evaluate_condition_expression(
            {"op": "==", "left": "a", "right": "a"},
            run=run,
            node_states={},
        )
        assert not evaluate_condition_expression(
            {"op": "==", "left": "a", "right": "b"},
            run=run,
            node_states={},
        )

    def test_in_operator(self):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun(input_files={})
        assert evaluate_condition_expression(
            {"op": "in", "left": "b", "right": ["a", "b", "c"]},
            run=run,
            node_states={},
        )
        assert not evaluate_condition_expression(
            {"op": "in", "left": "z", "right": ["a", "b", "c"]},
            run=run,
            node_states={},
        )

    def test_contains_operator(self):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun(input_files={})
        assert evaluate_condition_expression(
            {"op": "contains", "left": ["a", "b", "c"], "right": "b"},
            run=run,
            node_states={},
        )

    def test_workflow_input_reference(self):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun(input_files={"mode": "fast"})
        assert evaluate_condition_expression(
            {"op": "==", "left": "workflow_input:mode", "right": "fast"},
            run=run,
            node_states={},
        )

    def test_node_output_reference(self):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun(input_files={})
        node_states = {
            "tool_1": {
                "status": "success",
                "semantic_outputs": {
                    "score": {"value": 0.9},
                },
            }
        }
        assert evaluate_condition_expression(
            {"op": ">", "left": "node:tool_1:score", "right": 0.5},
            run=run,
            node_states=node_states,
        )

    def test_unsupported_operator_raises(self):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun(input_files={})
        with pytest.raises(Exception) as exc_info:
            evaluate_condition_expression(
                {"op": "+", "left": 1, "right": 2},
                run=run,
                node_states={},
            )
        assert "unsupported" in str(exc_info.value).lower()


class TestDependenciesSatisfiedWithCondition:
    def test_active_true_branch_satisfied(self):
        definition = {
            "nodes": [
                {"id": "cond", "kind": "condition", "expression": {"op": "==", "left": "a", "right": "a"}},
                {"id": "tool_a", "kind": "tool", "tool_slug": "a"},
            ],
            "edges": [{"source": "cond", "target": "tool_a", "branch": "true"}],
        }
        node_states = {
            "cond": {"status": "success", "active_branch": "true"},
        }
        assert dependencies_satisfied(
            definition=definition,
            node_states=node_states,
            node_id="tool_a",
        )

    def test_inactive_true_branch_not_satisfied(self):
        definition = {
            "nodes": [
                {"id": "cond", "kind": "condition", "expression": {"op": "==", "left": "a", "right": "a"}},
                {"id": "tool_a", "kind": "tool", "tool_slug": "a"},
            ],
            "edges": [{"source": "cond", "target": "tool_a", "branch": "true"}],
        }
        node_states = {
            "cond": {"status": "success", "active_branch": "false"},
        }
        assert not dependencies_satisfied(
            definition=definition,
            node_states=node_states,
            node_id="tool_a",
        )

    def test_false_branch_satisfied_when_active(self):
        definition = {
            "nodes": [
                {"id": "cond", "kind": "condition", "expression": {"op": "==", "left": "a", "right": "a"}},
                {"id": "tool_b", "kind": "tool", "tool_slug": "b"},
            ],
            "edges": [{"source": "cond", "target": "tool_b", "branch": "false"}],
        }
        node_states = {
            "cond": {"status": "success", "active_branch": "false"},
        }
        assert dependencies_satisfied(
            definition=definition,
            node_states=node_states,
            node_id="tool_b",
        )
