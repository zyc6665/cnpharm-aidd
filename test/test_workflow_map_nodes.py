"""Workflow map node tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.services.workflow_condition_scheduler import schedule_condition_node  # noqa: E402
from app.services.workflow_dependencies import dependencies_satisfied  # noqa: E402
from app.services.workflow_map_items import resolve_map_items  # noqa: E402
from app.services.workflow_scheduler import reconcile_map_sub_tasks  # noqa: E402
from app.services.workflow_validation import (  # noqa: E402
    validate_map_node,
    validate_workflow_definition,
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


class TestMapNodeValidation:
    """Map 节点定义校验。"""

    def test_map_node_without_over_raises(self):
        definition = {
            "nodes": [
                {"id": "input", "kind": "input"},
                {"id": "map1", "kind": "map", "tool_slug": "t"},
                {"id": "tool_a", "kind": "tool", "tool_slug": "a"},
            ],
            "edges": [
                {"source": "input", "target": "map1"},
                {"source": "map1", "target": "tool_a"},
            ],
        }
        with pytest.raises(Exception) as exc_info:
            validate_workflow_definition(definition)
        assert "over" in str(exc_info.value).lower()

    def test_map_node_with_over_validates_ok(self):
        definition = {
            "nodes": [
                {"id": "input", "kind": "input"},
                {
                    "id": "map1",
                    "kind": "map",
                    "over": "workflow_input:smiles_list",
                    "tool_slug": "molp-pc-property-prediction",
                },
                {"id": "tool_a", "kind": "tool", "tool_slug": "a"},
            ],
            "edges": [
                {"source": "input", "target": "map1"},
                {"source": "map1", "target": "tool_a"},
            ],
        }
        order = validate_workflow_definition(definition)
        assert "map1" in order

    def test_map_node_max_parallelism_validation(self):
        with pytest.raises(Exception) as exc_info:
            validate_map_node({
                "id": "m1", "kind": "map", "over": "x",
                "max_parallelism": 0,
            })
        assert "max_parallelism" in str(exc_info.value).lower()

    def test_map_node_in_execution_order_before_downstream(self):
        definition = {
            "nodes": [
                {"id": "input", "kind": "input"},
                {
                    "id": "map1",
                    "kind": "map",
                    "over": "workflow_input:items",
                    "tool_slug": "molp-pc-property-prediction",
                },
                {"id": "tool_a", "kind": "tool", "tool_slug": "a"},
            ],
            "edges": [
                {"source": "input", "target": "map1"},
                {"source": "map1", "target": "tool_a"},
            ],
        }
        order = validate_workflow_definition(definition)
        assert order.index("map1") < order.index("tool_a")


class TestResolveMapItems:
    """resolve_map_items 函数测试。"""

    @pytest.mark.asyncio
    async def test_workflow_input_list(self, db_session):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun(input_files={"items": ["a", "b", "c"]})
        result = await resolve_map_items(
            db_session, over="workflow_input:items",
            run=run, node_states={},
        )
        assert result == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_workflow_input_dict(self, db_session):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun(input_files={"items": {"k1": "v1", "k2": "v2"}})
        result = await resolve_map_items(
            db_session, over="workflow_input:items",
            run=run, node_states={},
        )
        assert result == ["v1", "v2"]

    @pytest.mark.asyncio
    async def test_workflow_input_single_item(self, db_session):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun(input_files={"items": "only_one"})
        result = await resolve_map_items(
            db_session, over="workflow_input:items",
            run=run, node_states={},
        )
        assert result == ["only_one"]

    @pytest.mark.asyncio
    async def test_workflow_input_missing_key(self, db_session):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun(input_files={})
        result = await resolve_map_items(
            db_session, over="workflow_input:missing",
            run=run, node_states={},
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_node_output_array_value(self, db_session):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun(input_files={})
        node_states = {
            "tool_1": {
                "status": "success",
                "semantic_outputs": {
                    "smiles_list": {
                        "value": ["CCO", "CC(=O)Oc1ccccc1C(=O)O"],
                        "file_id": None,
                    }
                },
            }
        }
        result = await resolve_map_items(
            db_session, over="node:tool_1:smiles_list",
            run=run, node_states=node_states,
        )
        assert result == ["CCO", "CC(=O)Oc1ccccc1C(=O)O"]

    @pytest.mark.asyncio
    async def test_node_output_csv_file(self, db_session, tmp_path: Path):
        from app.models.workflows import WorkflowRun
        from app.models.files import File as FileModel

        csv_path = tmp_path / "smiles.csv"
        csv_path.write_text("SMILES,id\nCCO,mol_1\nCC(=O)Oc1ccccc1C(=O)O,mol_2\n")

        run = WorkflowRun(input_files={})
        node_states = {
            "tool_1": {
                "status": "success",
                "semantic_outputs": {
                    "smiles_csv": {
                        "value": None,
                        "file_id": "file123",
                    }
                },
            }
        }

        mock_file = FileModel(
            id="file123",
            filename="smiles.csv",
            storage_path=str(csv_path),
            size_bytes=csv_path.stat().st_size,
            sha256="abc123def",
        )
        db_session.add(mock_file)
        await db_session.flush()

        result = await resolve_map_items(
            db_session, over="node:tool_1:smiles_csv",
            run=run, node_states=node_states,
        )
        assert len(result) == 2
        assert result[0]["SMILES"] == "CCO"
        assert result[1]["SMILES"] == "CC(=O)Oc1ccccc1C(=O)O"

    @pytest.mark.asyncio
    async def test_invalid_over_reference_raises(self, db_session):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun(input_files={})
        with pytest.raises(ValidationException, match="Unsupported map over"):
            await resolve_map_items(
                db_session, over="invalid_ref:something",
                run=run, node_states={},
            )


class TestMapNodeDependencies:
    """Map 节点在 dependency map 中的行为。"""

    def test_map_downstream_depends_on_map_node(self):
        definition = {
            "nodes": [
                {"id": "input", "kind": "input"},
                {
                    "id": "map1",
                    "kind": "map",
                    "over": "workflow_input:items",
                    "tool_slug": "a",
                },
                {"id": "tool_b", "kind": "tool", "tool_slug": "b"},
            ],
            "edges": [
                {"source": "input", "target": "map1"},
                {"source": "map1", "target": "tool_b"},
            ],
        }
        deps = workflow_dependency_map(definition)
        assert "map1" in deps["tool_b"]

    def test_map_node_with_sub_tasks_satisfies_downstream(self):
        definition = {
            "nodes": [
                {
                    "id": "map1",
                    "kind": "map",
                    "over": "workflow_input:items",
                    "tool_slug": "a",
                },
                {"id": "tool_b", "kind": "tool", "tool_slug": "b"},
            ],
            "edges": [{"source": "map1", "target": "tool_b"}],
        }
        node_states = {
            "map1": {"status": "success"},
        }
        assert dependencies_satisfied(
            definition=definition,
            node_states=node_states,
            node_id="tool_b",
        )

    def test_map_node_waiting_not_satisfies_downstream(self):
        definition = {
            "nodes": [
                {
                    "id": "map1",
                    "kind": "map",
                    "over": "workflow_input:items",
                    "tool_slug": "a",
                },
                {"id": "tool_b", "kind": "tool", "tool_slug": "b"},
            ],
            "edges": [{"source": "map1", "target": "tool_b"}],
        }
        node_states = {
            "map1": {"status": "waiting_task"},
        }
        assert not dependencies_satisfied(
            definition=definition,
            node_states=node_states,
            node_id="tool_b",
        )


class TestReconcileMapSubTasks:
    """Map 子任务协调逻辑。"""

    @pytest.mark.asyncio
    async def test_all_sub_tasks_success(self, db_session):
        from app.models.workflows import WorkflowRun
        from app.models.tasks import Task, TaskStatus

        run = WorkflowRun()

        # Create finished tasks for sub-tasks
        for i in range(3):
            task = Task(
                id=f"task_map_{i}",
                tool_id="tool1",
                tool_version_id="v1",
                name=f"map[0][{i}]",
                status=TaskStatus.SUCCESS.value,
            )
            db_session.add(task)

        await db_session.flush()

        state = {
            "map_total": 3,
            "sub_tasks": {
                "map_node[0]": {"task_id": "task_map_0", "status": "running"},
                "map_node[1]": {"task_id": "task_map_1", "status": "running"},
                "map_node[2]": {"task_id": "task_map_2", "status": "running"},
            },
        }
        node_states = {"map_node": state}

        await reconcile_map_sub_tasks(
            db_session,
            node_id="map_node",
            state=state,
            node_states=node_states,
            run=run,
        )

        assert state["status"] == "success"
        assert state["map_completed"] == 3
        assert state["map_failed"] == 0

    @pytest.mark.asyncio
    async def test_mixed_sub_tasks_partial_completion(self, db_session):
        from app.models.workflows import WorkflowRun
        from app.models.tasks import Task, TaskStatus

        run = WorkflowRun()

        success_task = Task(
            id="task_ok", tool_id="tool1", tool_version_id="v1",
            name="ok", status=TaskStatus.SUCCESS.value,
        )
        running_task = Task(
            id="task_running", tool_id="tool1", tool_version_id="v1",
            name="running", status=TaskStatus.RUNNING.value,
        )
        db_session.add_all([success_task, running_task])
        await db_session.flush()

        state = {
            "status": "waiting_task",
            "map_total": 2,
            "sub_tasks": {
                "map_node[0]": {"task_id": "task_ok", "status": "waiting_task"},
                "map_node[1]": {"task_id": "task_running", "status": "waiting_task"},
            },
        }
        node_states = {"map_node": state}

        await reconcile_map_sub_tasks(
            db_session,
            node_id="map_node",
            state=state,
            node_states=node_states,
            run=run,
        )

        assert state["status"] == "waiting_task"  # not all done
        assert state["map_completed"] == 1
        assert state["map_failed"] == 0
        assert state["sub_tasks"]["map_node[0]"]["status"] == "success"
        assert state["sub_tasks"]["map_node[1]"]["status"] == "running"

    @pytest.mark.asyncio
    async def test_failed_sub_task_marks_map_as_failure(self, db_session):
        from app.models.workflows import WorkflowRun
        from app.models.tasks import Task, TaskStatus

        run = WorkflowRun()

        fail_task = Task(
            id="task_fail", tool_id="tool1", tool_version_id="v1",
            name="fail", status=TaskStatus.FAILURE.value,
            error_message="Something broke",
        )
        db_session.add(fail_task)
        await db_session.flush()

        state = {
            "map_total": 1,
            "sub_tasks": {
                "map_node[0]": {"task_id": "task_fail", "status": "waiting_task"},
            },
        }
        node_states = {"map_node": state}

        await reconcile_map_sub_tasks(
            db_session,
            node_id="map_node",
            state=state,
            node_states=node_states,
            run=run,
        )

        assert state["status"] == "failure"
        assert state["map_completed"] == 0
        assert state["map_failed"] == 1

    @pytest.mark.asyncio
    async def test_no_sub_tasks_returns_false(self, db_session):
        from app.models.workflows import WorkflowRun

        run = WorkflowRun()
        state = {"status": "waiting_task"}
        node_states = {"map_node": state}

        changed = await reconcile_map_sub_tasks(
            db_session,
            node_id="map_node",
            state=state,
            node_states=node_states,
            run=run,
        )
        assert changed is False


class TestScheduleConditionNode:
    """Condition 节点调度集成测试。"""

    def test_schedule_condition_true_branch(self):
        from app.models.workflows import WorkflowRun

        definition = {
            "nodes": [
                {"id": "cond", "kind": "condition", "expression": {"op": "==", "left": "x", "right": "x"}},
                {"id": "tool_a", "kind": "tool", "tool_slug": "a"},
                {"id": "tool_b", "kind": "tool", "tool_slug": "b"},
            ],
            "edges": [
                {"source": "cond", "target": "tool_a", "branch": "true"},
                {"source": "cond", "target": "tool_b", "branch": "false"},
            ],
        }
        run = WorkflowRun(definition=definition, input_files={})
        node_states = {
            "cond": {"status": "pending"},
            "tool_a": {"status": "pending"},
            "tool_b": {"status": "pending"},
        }
        import asyncio

        async def _run():
            await schedule_condition_node(
                run=run,
                node_id="cond",
                node={"id": "cond", "kind": "condition", "expression": {"op": "==", "left": "x", "right": "x"}},
                node_states=node_states,
            )

        asyncio.run(_run())

        assert node_states["cond"]["status"] == "success"
        assert node_states["cond"]["active_branch"] == "true"
        assert node_states["tool_b"]["status"] == "skipped"
        assert node_states["tool_a"]["status"] == "pending"

    def test_schedule_condition_false_branch(self):
        from app.models.workflows import WorkflowRun

        definition = {
            "nodes": [
                {"id": "cond", "kind": "condition", "expression": {"op": "!=", "left": "x", "right": "x"}},
                {"id": "tool_a", "kind": "tool", "tool_slug": "a"},
                {"id": "tool_b", "kind": "tool", "tool_slug": "b"},
            ],
            "edges": [
                {"source": "cond", "target": "tool_a", "branch": "true"},
                {"source": "cond", "target": "tool_b", "branch": "false"},
            ],
        }
        run = WorkflowRun(definition=definition, input_files={})
        node_states = {
            "cond": {"status": "pending"},
            "tool_a": {"status": "pending"},
            "tool_b": {"status": "pending"},
        }
        import asyncio

        async def _run():
            await schedule_condition_node(
                run=run,
                node_id="cond",
                node={"id": "cond", "kind": "condition", "expression": {"op": "!=", "left": "x", "right": "x"}},
                node_states=node_states,
            )

        asyncio.run(_run())

        assert node_states["cond"]["status"] == "success"
        assert node_states["cond"]["active_branch"] == "false"
        assert node_states["tool_a"]["status"] == "skipped"
        assert node_states["tool_b"]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_schedule_condition_skips_inactive_branch_descendants(self):
        from app.models.workflows import WorkflowRun

        definition = {
            "nodes": [
                {"id": "cond", "kind": "condition", "expression": {"op": "==", "left": "x", "right": "x"}},
                {"id": "active_tool", "kind": "tool", "tool_slug": "active"},
                {"id": "inactive_tool", "kind": "tool", "tool_slug": "inactive"},
                {"id": "inactive_child", "kind": "tool", "tool_slug": "child"},
                {"id": "inactive_grandchild", "kind": "tool", "tool_slug": "grandchild"},
            ],
            "edges": [
                {"source": "cond", "target": "active_tool", "branch": "true"},
                {"source": "cond", "target": "inactive_tool", "branch": "false"},
                {"source": "inactive_tool", "target": "inactive_child"},
                {"source": "inactive_child", "target": "inactive_grandchild"},
            ],
        }
        run = WorkflowRun(definition=definition, input_files={})
        node_states = {
            "cond": {"status": "pending"},
            "active_tool": {"status": "pending"},
            "inactive_tool": {"status": "pending"},
            "inactive_child": {"status": "pending"},
            "inactive_grandchild": {"status": "pending"},
        }
        await schedule_condition_node(
            run=run,
            node_id="cond",
            node={"id": "cond", "kind": "condition", "expression": {"op": "==", "left": "x", "right": "x"}},
            node_states=node_states,
        )

        assert node_states["active_tool"]["status"] == "pending"
        assert node_states["inactive_tool"]["status"] == "skipped"
        assert node_states["inactive_child"]["status"] == "skipped"
        assert node_states["inactive_grandchild"]["status"] == "skipped"


class TestStartReadyWorkflowNodes:
    """start_ready_workflow_nodes 集成测试 - 轻量验证 dispatch 路径。"""

    @pytest.mark.asyncio
    async def test_map_node_is_recognized_by_is_map_node(self):
        """确认 map 节点被正确识别（无需完整 DB 集成）。"""
        node = {"id": "m1", "kind": "map", "over": "workflow_input:x", "tool_slug": "t"}
        from app.services.workflow_validation import is_map_node
        assert is_map_node(node) is True
