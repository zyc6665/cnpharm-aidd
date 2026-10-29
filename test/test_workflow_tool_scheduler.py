"""Workflow tool node scheduling module tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models.workflows import WorkflowRun  # noqa: E402
from app.services import workflow_loop_scheduler as loop_scheduler_mod  # noqa: E402
from app.services import workflow_map_scheduler as map_scheduler_mod  # noqa: E402
from app.services import workflow_tool_scheduler as scheduler_mod  # noqa: E402
from app.services.workflow_tool_scheduler import schedule_workflow_node  # noqa: E402


@pytest.mark.asyncio
async def test_schedule_workflow_node_keeps_existing_task_waiting():
    node_states = {"score": {"status": "pending", "task_id": "task-1"}}

    scheduled = await schedule_workflow_node(
        None,
        current_user=None,
        run=WorkflowRun(),
        node_id="score",
        node={"id": "score", "kind": "tool", "tool_slug": "score"},
        node_states=node_states,
        schedule_task_fn=None,
    )

    assert scheduled is False
    assert node_states["score"] == {"status": "waiting_task", "task_id": "task-1"}


@pytest.mark.asyncio
async def test_schedule_workflow_node_uses_pinned_tool_version(monkeypatch):
    """工具发新版本后，已建 run 的后续节点仍使用建 run 时的快照版本。"""
    tool = SimpleNamespace(
        id="tool-1",
        slug="score",
        current_version_id="version-2",
        current_version=SimpleNamespace(version="2.0.0"),
    )

    async def fake_load(db, *, node):
        return tool

    async def fake_prepare(db, **kwargs):
        return SimpleNamespace(
            binding_decisions={},
            ready=True,
            file_ids=[],
            input_bindings={},
            params=kwargs["params"],
            standard_input_uploads={},
        )

    async def fake_find(db, **kwargs):
        return None

    captured: dict = {}

    async def fake_schedule_task(**kwargs):
        captured["task_data"] = kwargs["task_data"]
        return SimpleNamespace(id="task-snap")

    monkeypatch.setattr(scheduler_mod, "load_available_workflow_tool", fake_load)
    monkeypatch.setattr(scheduler_mod, "prepare_workflow_node_run", fake_prepare)
    monkeypatch.setattr(scheduler_mod, "find_existing_workflow_node_task", fake_find)

    snapshot = {"id": "version-1", "version": "1.0.0"}
    node = {
        "id": "score",
        "kind": "tool",
        "tool_id": "tool-1",
        "tool_slug": "score",
        "tool_version": snapshot,
    }
    node_states = {"score": {"status": "pending", "tool_version_id": "version-1", "tool_version": snapshot}}
    run = SimpleNamespace(
        id="run-1",
        name="Snapshot Run",
        workflow_definition_id="workflow-1",
        project_id=None,
        input_files={},
    )

    created = await schedule_workflow_node(
        None,
        current_user=None,
        run=run,
        node_id="score",
        node=node,
        node_states=node_states,
        schedule_task_fn=fake_schedule_task,
    )

    assert created is True
    assert captured["task_data"].tool_version_id == "version-1"
    assert node_states["score"]["tool_version_id"] == "version-1"
    assert node_states["score"]["tool_version"]["version"] == "1.0.0"


def _stub_prepare():
    async def fake_prepare(db, **kwargs):
        return SimpleNamespace(
            binding_decisions={},
            ready=True,
            file_ids=[],
            input_bindings={},
            params=kwargs["params"],
            standard_input_uploads={},
        )

    return fake_prepare


@pytest.mark.asyncio
async def test_schedule_loop_node_uses_pinned_tool_version(monkeypatch):
    """loop body 在工具发新版后仍使用建 run 时快照的版本。"""
    tool = SimpleNamespace(
        id="tool-loop",
        slug="score",
        current_version_id="version-2",
        current_version=SimpleNamespace(version="2.0.0"),
    )

    async def fake_load(db, *, node):
        return tool

    async def fake_find(db, **kwargs):
        return None

    captured: dict = {}

    async def fake_schedule_task(**kwargs):
        captured["task_data"] = kwargs["task_data"]
        return SimpleNamespace(id="task-loop")

    monkeypatch.setattr(loop_scheduler_mod, "load_available_workflow_tool", fake_load)
    monkeypatch.setattr(loop_scheduler_mod, "prepare_workflow_node_run", _stub_prepare())
    monkeypatch.setattr(loop_scheduler_mod, "find_existing_workflow_node_task", fake_find)

    snapshot = {"id": "version-1", "version": "1.0.0"}
    node = {
        "id": "loop_score",
        "kind": "loop",
        "max_iterations": 3,
        "body": [
            {
                "id": "score",
                "kind": "tool",
                "tool_id": "tool-loop",
                "tool_slug": "score",
                "tool_version": snapshot,
            }
        ],
    }
    node_states = {"loop_score": {"status": "pending"}}
    run = SimpleNamespace(
        id="run-loop",
        name="Loop Run",
        workflow_definition_id="workflow-1",
        project_id=None,
        input_files={},
    )

    created = await loop_scheduler_mod.schedule_loop_node(
        None,
        current_user=None,
        run=run,
        node_id="loop_score",
        node=node,
        node_states=node_states,
        schedule_task_fn=fake_schedule_task,
    )

    assert created is True
    assert captured["task_data"].tool_version_id == "version-1"


@pytest.mark.asyncio
async def test_schedule_map_node_uses_pinned_tool_version(monkeypatch):
    """map 子任务在工具发新版后仍使用建 run 时快照的版本。"""
    tool = SimpleNamespace(
        id="tool-map",
        slug="score",
        current_version_id="version-2",
        current_version=SimpleNamespace(version="2.0.0"),
    )

    async def fake_load(db, *, node):
        return tool

    async def fake_find(db, **kwargs):
        return None

    async def fake_resolve_items(db, **kwargs):
        return [{"ligand": "a"}]

    captured: list = []

    async def fake_schedule_task(**kwargs):
        captured.append(kwargs["task_data"])
        return SimpleNamespace(id=f"task-map-{len(captured)}")

    monkeypatch.setattr(map_scheduler_mod, "load_available_workflow_tool", fake_load)
    monkeypatch.setattr(map_scheduler_mod, "prepare_workflow_node_run", _stub_prepare())
    monkeypatch.setattr(map_scheduler_mod, "find_existing_workflow_node_task", fake_find)
    monkeypatch.setattr(map_scheduler_mod, "resolve_map_items", fake_resolve_items)

    snapshot = {"id": "version-1", "version": "1.0.0"}
    node = {
        "id": "map_score",
        "kind": "map",
        "over": "workflow_input:items",
        "max_parallelism": 2,
        "tool_id": "tool-map",
        "tool_slug": "score",
        "tool_version": snapshot,
    }
    node_states = {"map_score": {"status": "pending"}}
    run = SimpleNamespace(
        id="run-map",
        name="Map Run",
        workflow_definition_id="workflow-1",
        project_id=None,
        input_files={"items": ["a"]},
    )

    created = await map_scheduler_mod.schedule_map_node(
        None,
        current_user=None,
        run=run,
        node_id="map_score",
        node=node,
        node_states=node_states,
        schedule_task_fn=fake_schedule_task,
    )

    assert created is True
    assert captured[0].tool_version_id == "version-1"
