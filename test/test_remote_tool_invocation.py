from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.remote_tools.invocation import (
    build_remote_tool_invoke_payload,
    remote_tool_parameters,
)


def test_remote_tool_parameters_prefers_nested_parameters_object() -> None:
    assert remote_tool_parameters({"parameters": {"threshold": 0.5}, "ignored": True}) == {
        "threshold": 0.5
    }
    assert remote_tool_parameters({"threshold": 0.5}) == {"threshold": 0.5}
    assert remote_tool_parameters(None) == {}
    assert remote_tool_parameters(["not", "params"]) == {}


def test_build_remote_tool_invoke_payload_wraps_task_inputs_parameters_and_context() -> None:
    payload = build_remote_tool_invoke_payload(
        request_id="request-1",
        task_id="task-1",
        tool_slug="remote-docking",
        tool_version="1.0.0",
        inputs={"protein": {"type": "protein_structure@1"}},
        parameters={"threshold": 0.5},
        project_id="project-1",
        user_id="user-1",
    )

    assert payload == {
        "request_id": "request-1",
        "task": {
            "id": "task-1",
            "tool_slug": "remote-docking",
            "tool_version": "1.0.0",
        },
        "inputs": {"protein": {"type": "protein_structure@1"}},
        "parameters": {"threshold": 0.5},
        "context": {"project_id": "project-1", "user_id": "user-1"},
    }


def test_remote_invoke_run_id_requires_non_empty_remote_run_id() -> None:
    from app.remote_tools import invocation

    run_id = getattr(invocation, "remote_invoke_run_id", None)

    assert callable(run_id)
    assert run_id({"remote_run_id": " run-1 "}) == "run-1"
    with pytest.raises(ValueError, match="Remote tool invoke response missing remote_run_id"):
        run_id({"remote_run_id": ""})


def test_recorded_remote_run_id_normalizes_task_extra_data() -> None:
    from app.remote_tools import invocation

    recorded_run_id = getattr(invocation, "recorded_remote_run_id", None)

    assert callable(recorded_run_id)
    assert recorded_run_id({"remote_run_id": " run-1 "}) == "run-1"
    assert recorded_run_id({"remote_run_id": ""}) is None
    assert recorded_run_id(None) is None
