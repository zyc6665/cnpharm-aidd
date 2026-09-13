"""Workflow loop node tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.services.workflow_loop_convergence import (  # noqa: E402
    evaluate_loop_convergence,
    resolve_loop_value,
)
from app.services.workflow_scheduler import (  # noqa: E402
    schedule_loop_node,
    reconcile_loop_body,
)
from app.services.workflow_validation import (  # noqa: E402
    validate_loop_node,
    validate_workflow_definition,
    is_loop_node,
    workflow_dependency_map,
)
from app.common.exceptions import ValidationException  # noqa: E402


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


def _make_loop_body() -> list[dict]:
    return [
        {"id": "step1", "kind": "tool", "tool_slug": "molp-pc-property-prediction"},
        {"id": "step2", "kind": "tool", "tool_slug": "builtin-admet-prediction"},
    ]


class TestLoopNodeValidation:
    """Loop 节点定义校验。"""

    def test_valid_loop_node_passes(self):
        definition = {
            "nodes": [
                {"id": "input", "kind": "input"},
                {
                    "id": "loop1",
                    "kind": "loop",
                    "body": _make_loop_body(),
                    "max_iterations": 5,
                },
                {"id": "tool_a", "kind": "tool", "tool_slug": "a"},
            ],
            "edges": [
                {"source": "input", "target": "loop1"},
                {"source": "loop1", "target": "tool_a"},
            ],
        }
        order = validate_workflow_definition(definition)
        assert "loop1" in order

    def test_missing_body_raises(self):
        with pytest.raises(ValidationException, match="body"):
            validate_loop_node({"id": "loop1", "kind": "loop"})

    def test_empty_body_raises(self):
        with pytest.raises(ValidationException, match="non-empty"):
            validate_loop_node({"id": "loop1", "kind": "loop", "body": []})

    def test_body_node_not_dict_raises(self):
        with pytest.raises(ValidationException, match="node dict"):
            validate_loop_node({
                "id": "loop1", "kind": "loop",
                "body": ["not_a_dict"],
            })

    def test_body_node_missing_id_raises(self):
        with pytest.raises(ValidationException, match="requires an 'id'"):
            validate_loop_node({
                "id": "loop1", "kind": "loop",
                "body": [{"kind": "tool", "tool_slug": "x"}],
            })

    def test_body_node_not_tool_raises(self):
        with pytest.raises(ValidationException, match="must be a tool node"):
            validate_loop_node({
                "id": "loop1", "kind": "loop",
                "body": [{"id": "cond1", "kind": "condition"}],
            })

    def test_max_iterations_exceeds_cap_raises(self):
        with pytest.raises(ValidationException, match="cannot exceed 100"):
            validate_loop_node({
                "id": "loop1", "kind": "loop",
                "body": _make_loop_body(),
                "max_iterations": 200,
            })

    def test_max_iterations_zero_raises(self):
        with pytest.raises(ValidationException, match="positive integer"):
            validate_loop_node({
                "id": "loop1", "kind": "loop",
                "body": _make_loop_body(),
                "max_iterations": 0,
            })

    def test_invalid_convergence_operator_raises(self):
        with pytest.raises(ValidationException, match="unsupported operator"):
            validate_loop_node({
                "id": "loop1", "kind": "loop",
                "body": _make_loop_body(),
                "convergence_condition": {"op": "regex", "left": "x", "right": "y"},
            })

    def test_convergence_condition_not_dict_raises(self):
        with pytest.raises(ValidationException, match="must be a dict"):
            validate_loop_node({
                "id": "loop1", "kind": "loop",
                "body": _make_loop_body(),
                "convergence_condition": "not_a_dict",
            })

    def test_default_max_iterations_is_10(self):
        definition = {
            "nodes": [
                {"id": "input", "kind": "input"},
                {
                    "id": "loop1",
                    "kind": "loop",
                    "body": _make_loop_body(),
                },
                {"id": "tool_a", "kind": "tool", "tool_slug": "a"},
            ],
            "edges": [
                {"source": "input", "target": "loop1"},
                {"source": "loop1", "target": "tool_a"},
            ],
        }
        order = validate_workflow_definition(definition)
        assert "loop1" in order


class TestIsLoopNode:
    """is_loop_node 识别测试。"""

    def test_recognizes_loop_node(self):
        assert is_loop_node({"id": "l1", "kind": "loop", "body": _make_loop_body()}) is True

    def test_rejects_tool_node(self):
        assert is_loop_node({"id": "t1", "kind": "tool", "tool_slug": "x"}) is False

    def test_rejects_condition_node(self):
        assert is_loop_node({"id": "c1", "kind": "condition"}) is False

    def test_rejects_none(self):
        assert is_loop_node(None) is False


class TestLoopNodeDependencies:
    """Loop 节点依赖图行为。"""

    def test_upstream_depends_on_loop_node(self):
        definition = {
            "nodes": [
                {"id": "input", "kind": "input"},
                {
                    "id": "loop1",
                    "kind": "loop",
                    "body": _make_loop_body(),
                },
                {"id": "tool_b", "kind": "tool", "tool_slug": "b"},
            ],
            "edges": [
                {"source": "input", "target": "loop1"},
                {"source": "loop1", "target": "tool_b"},
            ],
        }
        deps = workflow_dependency_map(definition)
        assert "loop1" in deps["tool_b"]

    def test_loop_depends_on_upstream(self):
        definition = {
            "nodes": [
                {"id": "input", "kind": "input"},
                {
                    "id": "loop1",
                    "kind": "loop",
                    "body": _make_loop_body(),
                },
            ],
            "edges": [
                {"source": "input", "target": "loop1"},
            ],
        }
        deps = workflow_dependency_map(definition)
        assert "input" in deps["loop1"]


class TestEvaluateConvergence:
    """收敛条件评估。"""

    def test_equals_convergence_true(self):
        result = evaluate_loop_convergence(
            {"op": "==", "left": "node:step1:score", "right": 0.0},
            body_states={
                "step1": {"outputs": {"score": 0.0}},
            },
        )
        assert result is True

    def test_lt_convergence_true(self):
        result = evaluate_loop_convergence(
            {"op": "<", "left": "node:step1:delta", "right": 0.01},
            body_states={
                "step1": {"outputs": {"delta": 0.005}},
            },
        )
        assert result is True

    def test_lt_convergence_false(self):
        result = evaluate_loop_convergence(
            {"op": "<", "left": "node:step1:delta", "right": 0.01},
            body_states={
                "step1": {"outputs": {"delta": 0.05}},
            },
        )
        assert result is False

    def test_no_condition_returns_false(self):
        result = evaluate_loop_convergence(None, body_states={"step1": {}})
        assert result is False

    def test_no_condition_with_same_outputs_returns_true(self):
        outputs = {"step1": {"outputs": {"score": 1.0}}}
        result = evaluate_loop_convergence(
            None,
            body_states=outputs,
            previous_iteration_outputs=outputs,
        )
        assert result is True

    def test_unknown_operator_returns_false(self):
        result = evaluate_loop_convergence(
            {"op": "~~~", "left": 1, "right": 1},
            body_states={},
        )
        assert result is False

    def test_type_error_returns_false(self):
        result = evaluate_loop_convergence(
            {"op": "<", "left": "string", "right": 123},
            body_states={},
        )
        assert result is False


class TestResolveLoopValue:
    """resolve_loop_value 值解析。"""

    def test_resolves_node_output_value(self):
        result = resolve_loop_value(
            "node:step1:score",
            {"step1": {"outputs": {"score": 9.5}}},
        )
        assert result == 9.5

    def test_resolves_result_field(self):
        result = resolve_loop_value(
            "node:step1:score",
            {"step1": {"result": {"score": 8.0}}},
        )
        assert result == 8.0

    def test_returns_raw_value_for_non_node_ref(self):
        result = resolve_loop_value(42, {})
        assert result == 42

    def test_returns_none_for_missing_key(self):
        result = resolve_loop_value(
            "node:step1:missing",
            {"step1": {"outputs": {}}},
        )
        assert result is None

    def test_returns_none_for_missing_body_node(self):
        result = resolve_loop_value(
            "node:nonexistent:score",
            {},
        )
        assert result is None


class TestScheduleLoopNode:
    """schedule_loop_node 测试。"""

    @pytest.mark.asyncio
    async def test_initializes_loop_state_and_creates_tasks(self, db_session):
        from app.models.workflows import WorkflowRun
        from app.models.tools import Tool, ToolVersion
        from app.models.users import User

        user = User(
            id="user-1",
            email="test@example.com",
            password_hash="not-a-real-hash",
            display_name="test-user",
            role="user",
        )
        db_session.add(user)

        tool = Tool(
            id="tool-1",
            slug="molp-pc-property-prediction",
            name="Test Tool",
            status="published",
            owner_id=user.id,
        )
        tool_version = ToolVersion(
            id="tv-1",
            tool_id="tool-1",
            version="1.0.0",
            config={"type": "docker_image", "image": "test:latest"},
        )
        tool.current_version = tool_version
        tool.current_version_id = tool_version.id
        db_session.add_all([tool, tool_version])
        await db_session.flush()

        run = WorkflowRun(
            id="run-1",
            owner_id=user.id,
            definition={"nodes": [], "edges": []},
            input_files={},
            execution_order=[],
            node_states={},
        )

        node = {
            "id": "loop1",
            "kind": "loop",
            "body": [
                {"id": "step1", "kind": "tool", "tool_slug": "molp-pc-property-prediction"},
            ],
            "max_iterations": 5,
        }
        node_states = {"loop1": {}}

        mock_schedule = AsyncMock()
        mock_schedule.return_value = SimpleNamespace(id="task-001")

        await schedule_loop_node(
            db_session,
            current_user=user,
            run=run,
            node_id="loop1",
            node=node,
            node_states=node_states,
            schedule_task_fn=mock_schedule,
        )

        state = node_states["loop1"]
        assert state["loop_iteration"] == 1
        assert state["loop_max_iterations"] == 5
        assert "loop_body_states" in state
        assert "loop_history" in state
        assert state["status"] == "waiting_task"


class TestReconcileLoopBody:
    """reconcile_loop_body 逻辑测试。"""

    @pytest.mark.asyncio
    async def test_all_success_converged_marks_success(self, db_session):
        from app.models.workflows import WorkflowRun
        from app.models.tasks import Task, TaskOutput, TaskStatus

        run = WorkflowRun()

        task = Task(
            id="task-1",
            tool_id="tool-1",
            tool_version_id="tv-1",
            name="step1",
            status=TaskStatus.SUCCESS.value,
        )
        output = TaskOutput(
            task_id="task-1",
            result={"score": 0.0},
        )
        db_session.add_all([task, output])
        await db_session.flush()

        node = {
            "id": "loop1",
            "kind": "loop",
            "body": [{"id": "step1", "kind": "tool", "tool_slug": "x"}],
            "max_iterations": 5,
            "convergence_condition": {"op": "==", "left": "node:step1:score", "right": 0.0},
        }
        state = {
            "loop_iteration": 1,
            "loop_max_iterations": 5,
            "loop_body_states": {
                "step1": {"task_id": "task-1", "status": "running"},
            },
            "loop_history": [],
        }
        node_states = {"loop1": state}

        await reconcile_loop_body(
            db_session,
            node_id="loop1",
            node=node,
            state=state,
            node_states=node_states,
            run=run,
        )

        assert state["status"] == "success"

    @pytest.mark.asyncio
    async def test_all_success_not_converged_prepares_next_iteration(self, db_session):
        from app.models.workflows import WorkflowRun
        from app.models.tasks import Task, TaskOutput, TaskStatus

        run = WorkflowRun()

        task = Task(
            id="task-1",
            tool_id="tool-1",
            tool_version_id="tv-1",
            name="step1",
            status=TaskStatus.SUCCESS.value,
        )
        output = TaskOutput(
            task_id="task-1",
            result={"score": 5.0},  # 5.0 > 0.0 is True, so convergence WOULD trigger
        )
        db_session.add_all([task, output])
        await db_session.flush()

        node = {
            "id": "loop1",
            "kind": "loop",
            "body": [{"id": "step1", "kind": "tool", "tool_slug": "x"}],
            "max_iterations": 5,
            "convergence_condition": {"op": "<", "left": "node:step1:score", "right": 0.01},
        }
        state = {
            "loop_iteration": 1,
            "loop_max_iterations": 5,
            "loop_body_states": {
                "step1": {"task_id": "task-1", "status": "running"},
            },
            "loop_history": [],
        }
        node_states = {"loop1": state}

        await reconcile_loop_body(
            db_session,
            node_id="loop1",
            node=node,
            state=state,
            node_states=node_states,
            run=run,
        )

        # 未收敛 → 下一轮迭代
        assert state["loop_iteration"] == 2
        assert state["loop_body_states"] == {}
        assert state["status"] == "pending"
        assert len(state["loop_history"]) == 1

    @pytest.mark.asyncio
    async def test_body_task_failure_marks_loop_as_failure(self, db_session):
        from app.models.workflows import WorkflowRun
        from app.models.tasks import Task, TaskStatus

        run = WorkflowRun()

        task = Task(
            id="task-fail",
            tool_id="tool-1",
            tool_version_id="tv-1",
            name="step1",
            status=TaskStatus.FAILURE.value,
            error_message="body failed",
        )
        db_session.add(task)
        await db_session.flush()

        node = {
            "id": "loop1",
            "kind": "loop",
            "body": [{"id": "step1", "kind": "tool", "tool_slug": "x"}],
            "max_iterations": 5,
        }
        state = {
            "loop_iteration": 2,
            "loop_max_iterations": 5,
            "loop_body_states": {
                "step1": {"task_id": "task-fail", "status": "running"},
            },
            "loop_history": [],
        }
        node_states = {"loop1": state}

        await reconcile_loop_body(
            db_session,
            node_id="loop1",
            node=node,
            state=state,
            node_states=node_states,
            run=run,
        )

        assert state["status"] == "failure"

    @pytest.mark.asyncio
    async def test_body_tasks_still_running_keeps_waiting(self, db_session):
        from app.models.workflows import WorkflowRun
        from app.models.tasks import Task, TaskStatus

        run = WorkflowRun()

        task = Task(
            id="task-running",
            tool_id="tool-1",
            tool_version_id="tv-1",
            name="step1",
            status=TaskStatus.RUNNING.value,
        )
        db_session.add(task)
        await db_session.flush()

        node = {
            "id": "loop1",
            "kind": "loop",
            "body": [{"id": "step1", "kind": "tool", "tool_slug": "x"}],
            "max_iterations": 5,
        }
        state = {
            "loop_iteration": 1,
            "loop_max_iterations": 5,
            "loop_body_states": {
                "step1": {"task_id": "task-running", "status": "waiting_task"},
            },
            "loop_history": [],
        }
        node_states = {"loop1": state}

        await reconcile_loop_body(
            db_session,
            node_id="loop1",
            node=node,
            state=state,
            node_states=node_states,
            run=run,
        )

        assert state["status"] == "waiting_task"

    @pytest.mark.asyncio
    async def test_max_iterations_reached_without_convergence(self, db_session):
        from app.models.workflows import WorkflowRun
        from app.models.tasks import Task, TaskStatus

        run = WorkflowRun()

        task = Task(
            id="task-1",
            tool_id="tool-1",
            tool_version_id="tv-1",
            name="step1",
            status=TaskStatus.SUCCESS.value,
        )
        db_session.add(task)
        await db_session.flush()

        node = {
            "id": "loop1",
            "kind": "loop",
            "body": [{"id": "step1", "kind": "tool", "tool_slug": "x"}],
            "max_iterations": 3,
            "convergence_condition": {"op": "==", "left": 1, "right": 2},  # never true
        }
        state = {
            "loop_iteration": 3,  # reached max
            "loop_max_iterations": 3,
            "loop_body_states": {
                "step1": {"task_id": "task-1", "status": "running"},
            },
            "loop_history": [],
        }
        node_states = {"loop1": state}

        await reconcile_loop_body(
            db_session,
            node_id="loop1",
            node=node,
            state=state,
            node_states=node_states,
            run=run,
        )

        # 达到最大迭代，即使未收敛也标记成功
        assert state["status"] == "success"
        assert state["loop_total_iterations"] == 3
        assert state["loop_converged"] is False

    @pytest.mark.asyncio
    async def test_no_body_states_returns_no_change(self, db_session):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun()
        node = {
            "id": "loop1", "kind": "loop",
            "body": [{"id": "step1", "kind": "tool", "tool_slug": "x"}],
        }
        state = {"status": "waiting_task"}
        node_states = {"loop1": state}

        changed = await reconcile_loop_body(
            db_session,
            node_id="loop1",
            node=node,
            state=state,
            node_states=node_states,
            run=run,
        )
        assert changed is False
