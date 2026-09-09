from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "backend/scripts/run_at003_platform_smoke.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_at003_platform_smoke", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_at003_smoke_runner_creates_platform_task_and_writes_record(monkeypatch, tmp_path):
    module = _load_script_module()
    calls = []

    def fake_api_request(method, base_url, path, *, token, payload=None, timeout=30):
        calls.append((method, path, payload))
        if path == "/api/v1/tasks/prepare-preview":
            return {"data": {"ready": True}}
        if path == "/api/v1/tasks":
            return {"data": {"id": "task-molp-pc-1"}}
        if path == "/api/v1/tasks/task-molp-pc-1":
            return {"data": {"id": "task-molp-pc-1", "status": "success"}}
        raise AssertionError(path)

    monkeypatch.setattr(module, "_api_request", fake_api_request)
    monkeypatch.setattr(module, "collect_record", lambda *args: "# evidence\n")
    output_path = tmp_path / "record.md"

    result = module.run_smoke(
        base_url="http://platform.local",
        token="token",
        project_id="project-1",
        tool_id="tool-molp-pc",
        input_artifact_version_id="artifact-version-rdkit",
        output_path=output_path,
        poll_interval_sec=0,
        timeout_sec=10,
    )

    create_payload = calls[1][2]
    assert result["task_id"] == "task-molp-pc-1"
    assert output_path.read_text(encoding="utf-8") == "# evidence\n"
    assert calls[0][0:2] == ("POST", "/api/v1/tasks/prepare-preview")
    assert calls[1][0:2] == ("POST", "/api/v1/tasks")
    assert create_payload["input_bindings"] == {"molecules": "artifact-version-rdkit"}
    assert create_payload["params"] == {"task_groups": ["Absorption"]}
    assert "model/MolP-PC/platform_run.sh" not in str(create_payload)


def test_at003_smoke_runner_rejects_unready_preview(monkeypatch):
    module = _load_script_module()

    def fake_api_request(method, base_url, path, *, token, payload=None, timeout=30):
        return {"data": {"ready": False, "blocked_reason": "missing input"}}

    monkeypatch.setattr(module, "_api_request", fake_api_request)

    with pytest.raises(ValueError, match="missing input"):
        module.run_smoke(
            base_url="http://platform.local",
            token="token",
            project_id="project-1",
            tool_id="tool-molp-pc",
            input_artifact_version_id="artifact-version-rdkit",
            poll_interval_sec=0,
            timeout_sec=10,
        )
