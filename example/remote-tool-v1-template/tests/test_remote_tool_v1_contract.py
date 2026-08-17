"""Package-local Remote Tool v1 contract checks."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from service import create_app  # noqa: E402


def test_service_exposes_required_remote_tool_v1_endpoints():
    client = TestClient(create_app())

    manifest = client.get("/.well-known/sciminer-tool.json").json()
    examples = client.get("/examples").json()

    assert manifest["api_version"] == "aidd.sciminer/remote-tool.v1"
    assert manifest["kind"] == "RemoteTool"
    assert manifest["capabilities"]["async"] is True
    assert manifest["capabilities"]["logs"] is True
    assert manifest["capabilities"]["cancel"] is True
    assert examples["examples"][0]["smoke"] is True


def test_service_runs_async_lifecycle():
    client = TestClient(create_app())

    created = client.post(
        "/invoke",
        json={
            "request_id": "request-1",
            "task": {"id": "task-1", "tool_slug": "remote-pocket-demo", "tool_version": "1.0.0"},
            "inputs": {},
            "parameters": {"threshold": 0.5},
            "context": {},
        },
    ).json()

    run_id = created["remote_run_id"]
    assert created["status"] == "queued"
    assert client.get(f"/runs/{run_id}").json()["status"] == "running"
    assert client.get(f"/runs/{run_id}").json()["status"] == "success"
    assert client.get(f"/runs/{run_id}/logs").json()["items"]
    assert client.get(f"/runs/{run_id}/artifacts").json()["result_version"] == "aidd.sciminer/result.v2"
    assert client.post(f"/runs/{run_id}/cancel").json()["status"] == "canceled"
