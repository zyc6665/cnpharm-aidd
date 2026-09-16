from __future__ import annotations

import sys
from pathlib import Path


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
