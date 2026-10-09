"""Task executor integration with the managed Kubernetes Job gateway."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_kubernetes_job_executor_polls_gateway_and_collects_file_ids():
    from app.execution.contracts import ExecutionHandle, ExecutionState, ProducedArtifact
    from app.execution.contracts import ExecutionInput
    from app.execution.service import ExecutionService
    from app.tasks.executors.kubernetes_job import KubernetesJobExecutor

    calls: list[tuple] = []
    submitted_requests = []

    class Adapter:
        def __init__(self):
            self.states = iter((ExecutionState.QUEUED, ExecutionState.SUCCEEDED))

        async def submit(self, request):
            calls.append(("submit", request.executor_type, request.project_id))
            submitted_requests.append(request)
            return ExecutionHandle(
                execution_id="job-1",
                external_id="job-1",
                state=ExecutionState.QUEUED,
            )

        async def reconcile(self, execution_id):
            calls.append(("reconcile", execution_id))
            return next(self.states)

        async def logs(self, execution_id, cursor=None):
            return SimpleNamespace(content="", next_cursor=cursor)

        async def collect_artifacts(self, execution_id):
            calls.append(("collect", execution_id))
            return [ProducedArtifact(filename="result.json", path="outputs/result.json", file_id="file-1")]

        async def cancel(self, execution_id):
            calls.append(("cancel", execution_id))

    task = SimpleNamespace(
        id="task-1",
        user_id="user-1",
        tool_id="tool-1",
        tool_version_id="version-1",
        extra_data={"project_id": "project-1", "attempt_id": "attempt-1"},
        inputs=SimpleNamespace(params={"threshold": 0.5}),
    )
    tool_version = SimpleNamespace(
        id="version-1",
        version="1.0.0",
        config={
            "type": "k8s_job",
            "tool_slug": "managed-model",
            "tool_package_version_id": "package-version-1",
            "variant": "default",
            "runtime": {
                "image": "registry.example/model@sha256:" + "a" * 64,
                "entrypoint": ["/opt/sciminer/platform_adaptor/entrypoint.sh"],
            },
            "poll_interval_sec": 0,
        },
    )
    service = ExecutionService({"k8s_job": Adapter()})

    result = await KubernetesJobExecutor(
        task,
        tool_version,
        execution_service=service,
    ).execute()

    assert result["success"] is True
    assert result["output_file_ids"] == ["file-1"]
    assert task.extra_data["external_id"] == "job-1"
    request = submitted_requests[0]
    assert request.runtime["args"] == [
        "--task-id",
        "task-1",
        "--input-dir",
        "/workspace/input",
        "--output-dir",
        "/workspace/output",
        "--params-json",
        "/workspace/input/request.json",
        "--work-dir",
        "/workspace/work",
        "--device",
        "auto",
    ]
    request_payload = json.loads(request.runtime["env"]["SCIMINER_REQUEST_JSON"])
    assert request_payload["request_version"] == "aidd.sciminer/request.v1"
    assert request_payload["task"]["tool_slug"] == "managed-model"
    assert request_payload["parameters"] == {"threshold": 0.5}
    assert calls == [
        ("submit", "k8s_job", "project-1"),
        ("reconcile", "job-1"),
        ("reconcile", "job-1"),
        ("collect", "job-1"),
    ]


@pytest.mark.asyncio
async def test_kubernetes_request_contains_staged_standard_artifact_files_and_metadata():
    from app.execution.contracts import ExecutionInput
    from app.execution.service import ExecutionService
    from app.tasks.executors.kubernetes_job import KubernetesJobExecutor

    task = SimpleNamespace(
        id="task-2",
        user_id="user-1",
        tool_id="tool-1",
        tool_version_id="version-1",
        extra_data={"project_id": "project-1", "attempt_id": "attempt-2"},
        inputs=SimpleNamespace(params={"num_samples": 1}),
    )
    tool_version = SimpleNamespace(
        id="version-1",
        version="0.1.4-k8s",
        config={
            "type": "k8s_job",
            "tool_slug": "pocket2mol-pocket-ligand-generation",
            "variant": "nvidia-cuda",
            "runtime": {"image": "registry.example/model@sha256:" + "b" * 64},
        },
    )
    executor = KubernetesJobExecutor(
        task,
        tool_version,
        execution_service=ExecutionService({}),
    )

    async def stage_inputs(_attempt_id):
        return [
            ExecutionInput(
                artifact_version_id="artifact-version-1",
                name="pocket",
                uri="inputs/task-2/attempt-2/pocket/residue_pocket.pdb",
                sha256="c" * 64,
                role="residue_pocket_pdb",
                artifact_type="binding_pocket@1",
                content_type="chemical/x-pdb",
                metadata={"center": [32.0, 28.0, 36.0]},
            )
        ]

    executor._stage_inputs = stage_inputs
    request = await executor._build_request()
    payload = json.loads(request.runtime["env"]["SCIMINER_REQUEST_JSON"])

    assert payload["inputs"]["pocket"] == {
        "artifact_version_id": "artifact-version-1",
        "type": "binding_pocket@1",
        "files": {
            "residue_pocket_pdb": {
                "path": "input/pocket/residue_pocket.pdb",
                "sha256": "c" * 64,
                "content_type": "chemical/x-pdb",
            }
        },
        "metadata": {"center": [32.0, 28.0, 36.0]},
    }
    assert request.runtime["args"][-1] == "cuda"


@pytest.mark.asyncio
async def test_kubernetes_input_staging_runs_for_standard_bindings_without_task_file_ids(monkeypatch):
    from app.execution.contracts import ExecutionInput
    from app.storage import factory as storage_factory
    from app.tasks.executors import kubernetes_job
    from app.tasks.executors.kubernetes_job import KubernetesJobExecutor

    calls = []
    task = SimpleNamespace(
        id="task-3",
        tool_id="tool-1",
        tool_version_id="version-1",
        extra_data={"input_bindings": {"pocket": "artifact-version-1"}},
        inputs=SimpleNamespace(file_ids=[]),
    )
    tool_version = SimpleNamespace(
        id="version-1",
        config={"type": "k8s_job"},
    )
    executor = KubernetesJobExecutor(task, tool_version, db_session=object())

    async def fake_stage(db, *, task, attempt_id, storage, prefix):
        calls.append((db, task, attempt_id, storage, prefix))
        return [
            ExecutionInput(
                artifact_version_id="artifact-version-1",
                name="pocket",
                uri="inputs/task-3/attempt-1/pocket/pocket.pdb",
                sha256="a" * 64,
                role="residue_pocket_pdb",
                artifact_type="binding_pocket@1",
            )
        ]

    monkeypatch.setattr(kubernetes_job, "stage_kubernetes_inputs", fake_stage)
    monkeypatch.setattr(storage_factory, "get_storage_backend", lambda _: "storage")

    result = await executor._stage_inputs("attempt-1")

    assert result[0].name == "pocket"
    assert calls == [(executor.db_session, task, "attempt-1", "storage", "inputs")]
