"""Kubernetes Job disappearance: the handle outlives the Job object.

A managed Job can leave the cluster while the platform still holds its handle:
``ttlSecondsAfterFinished`` reclaims it, a cancellation deletes it, or an
operator deletes it by hand. Before this behaviour existed, every one of those
cases surfaced as ``KubernetesTransportError: HTTP 404`` and the worker turned
it into a task failure — including the TTL case, where the run had actually
succeeded and its artifacts were sitting in object storage.

The regression points are:
1. ``KubernetesHttpTransport`` raises ``ExecutionHandleGone`` on 404 instead of
   a generic transport error, and ``job_exists`` answers without raising.
2. The executor recovers a vanished Job whose result manifest is still readable
   and reports success instead of failure.
3. The executor reports an actionable failure when neither the Job nor the
   result manifest is available, keeping the task in a terminal state.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest


def _request():
    from app.execution.contracts import ExecutionRequest

    return ExecutionRequest(
        idempotency_key="task:task-1:attempt:attempt-1",
        project_id="project-1",
        requested_by="user-1",
        tool_package_version_id="package-version-1",
        variant="cpu",
        executor_type="k8s_job",
        runtime={
            "image": "registry.example/model@sha256:" + "a" * 64,
            "entrypoint": ["/app/run.sh"],
        },
        task_id="task-1",
        attempt_id="attempt-1",
        tool_version_id="tool-version-1",
    )


def _config():
    from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig

    return KubernetesJobExecutionConfig(
        cluster_alias="platform",
        namespace="model-jobs",
        credential_ref="k8s-credential",
        service_account="model-runner",
    )


def _credentials():
    from app.execution.adapters.kubernetes import KubernetesCredentials

    return KubernetesCredentials(
        api_server="https://kubernetes.default.svc",
        token="secret-token",
    )


# --------------------------------------------------------------------------- #
# Transport layer
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_transport_raises_handle_gone_on_missing_job():
    from app.execution.contracts import ExecutionHandleGone
    from app.execution.transports.kubernetes_http import KubernetesHttpTransport

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"reason": "NotFound", "message": "jobs.batch not found"},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = KubernetesHttpTransport(client=client)
    try:
        with pytest.raises(ExecutionHandleGone) as excinfo:
            await transport.status(
                "model-jobs/gone-job", _config(), _credentials()
            )
    finally:
        await client.aclose()

    assert "gone-job" in str(excinfo.value)
    # A vanished Job is a known terminal outcome, not a transport failure, so
    # callers can map it to a terminal state instead of retrying it.
    from app.execution.transports.kubernetes_http import KubernetesTransportError

    assert not isinstance(excinfo.value, KubernetesTransportError)


@pytest.mark.asyncio
async def test_transport_job_exists_answers_without_raising():
    from app.execution.transports.kubernetes_http import KubernetesHttpTransport

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/gone-job"):
            return httpx.Response(404, json={"reason": "NotFound"}, request=request)
        return httpx.Response(
            200, json={"status": {"active": 1}}, request=request
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = KubernetesHttpTransport(client=client)
    try:
        assert await transport.job_exists(
            "model-jobs/live-job", _config(), _credentials()
        ) is True
        assert await transport.job_exists(
            "model-jobs/gone-job", _config(), _credentials()
        ) is False
    finally:
        await client.aclose()


# --------------------------------------------------------------------------- #
# Adapter / service layer
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_adapter_exists_returns_true_when_transport_cannot_answer():
    from app.execution.adapters.kubernetes import KubernetesJobExecutionAdapter

    class TransportWithoutExistenceCheck:
        async def submit(self, request, config, credentials):  # pragma: no cover
            raise AssertionError("not used")

    adapter = KubernetesJobExecutionAdapter(
        config=_config(),
        secret_provider=_StubSecretProvider(),
        transport=TransportWithoutExistenceCheck(),
    )

    # Older transports (and most test doubles) do not implement job_exists. The
    # adapter must keep the previous behaviour instead of inventing a terminal
    # state from a missing answer.
    assert await adapter.exists("model-jobs/whatever") is True


@pytest.mark.asyncio
async def test_service_execution_exists_defaults_to_true_for_plain_adapters():
    from app.execution.contracts import ExecutionHandle, ExecutionState
    from app.execution.service import ExecutionService

    class PlainAdapter:
        async def submit(self, request):  # pragma: no cover
            return ExecutionHandle(execution_id="x", state=ExecutionState.QUEUED)

        async def status(self, execution_id):  # pragma: no cover
            return ExecutionState.RUNNING

        async def logs(self, execution_id, cursor=None):  # pragma: no cover
            return None

        async def collect_artifacts(self, execution_id):  # pragma: no cover
            return []

        async def cancel(self, execution_id):  # pragma: no cover
            return None

    service = ExecutionService({"k8s_job": PlainAdapter()})

    assert await service.execution_exists("k8s_job", "whatever") is True


# --------------------------------------------------------------------------- #
# Executor layer
# --------------------------------------------------------------------------- #


class _StubSecretProvider:
    async def resolve(self, reference: str):
        return _credentials()


def _tool_version(**overrides):
    config = {
        "type": "k8s_job",
        "tool_slug": "managed-model",
        "tool_package_version_id": "package-version-1",
        "variant": "default",
        "runtime": {
            "image": "registry.example/model@sha256:" + "a" * 64,
            "entrypoint": ["/opt/sciminer/platform_adaptor/entrypoint.sh"],
        },
        "poll_interval_sec": 0,
    }
    config.update(overrides)
    return SimpleNamespace(id="version-1", version="1.0.0", config=config)


def _task(**overrides):
    values = {
        "id": "task-gone",
        "user_id": "user-1",
        "tool_id": "tool-1",
        "tool_version_id": "version-1",
        "extra_data": {"project_id": "project-1", "attempt_id": "attempt-1"},
        "inputs": SimpleNamespace(params={"threshold": 0.5}),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _VanishingAdapter:
    """Submits a Job, then reports it gone on the first reconcile."""

    def __init__(self, *, result_available: bool):
        self.result_available = result_available
        self.calls: list[tuple] = []

    async def submit(self, request):
        from app.execution.contracts import ExecutionHandle, ExecutionState

        self.calls.append(("submit",))
        return ExecutionHandle(
            execution_id="job-gone",
            external_id="job-gone",
            state=ExecutionState.QUEUED,
        )

    async def reconcile(self, execution_id):
        from app.execution.contracts import ExecutionHandleGone

        self.calls.append(("reconcile", execution_id))
        raise ExecutionHandleGone(f"Kubernetes Job no longer exists: {execution_id}")

    async def collect_result(self, execution_id):
        from app.execution.contracts import ExecutionArtifactCollection, ProducedArtifact

        self.calls.append(("collect_result", execution_id))
        if not self.result_available:
            raise RuntimeError("failed to download Kubernetes result manifest")
        return ExecutionArtifactCollection(
            artifacts=(
                ProducedArtifact(
                    filename="result.json",
                    path="outputs/result.json",
                    file_id="file-1",
                ),
            ),
            result_payload={"request_version": "aidd.sciminer/result"},
        )

    async def logs(self, execution_id, cursor=None):  # pragma: no cover
        return SimpleNamespace(content="", next_cursor=cursor)

    async def collect_artifacts(self, execution_id):  # pragma: no cover
        return []

    async def cancel(self, execution_id):  # pragma: no cover
        self.calls.append(("cancel", execution_id))


@pytest.mark.asyncio
async def test_executor_recovers_result_when_job_vanished_after_ttl():
    from app.execution.service import ExecutionService
    from app.tasks.executors.kubernetes_job import KubernetesJobExecutor

    adapter = _VanishingAdapter(result_available=True)
    executor = KubernetesJobExecutor(
        _task(),
        _tool_version(),
        execution_service=ExecutionService({"k8s_job": adapter}),
    )

    result = await executor.execute()

    assert result["success"] is True
    assert result["state"] == "succeeded"
    assert result["output_file_ids"] == ["file-1"]
    assert result["result"]["request_version"] == "aidd.sciminer/result"
    # The result is collected exactly once: the recovery path returns it and the
    # normal path reuses it instead of downloading the manifest a second time.
    assert [call[0] for call in adapter.calls] == ["submit", "reconcile", "collect_result"]


@pytest.mark.asyncio
async def test_executor_fails_actionably_when_job_and_result_are_both_gone():
    from app.execution.service import ExecutionService
    from app.tasks.executors.errors import TaskExecutionError
    from app.tasks.executors.kubernetes_job import KubernetesJobExecutor

    adapter = _VanishingAdapter(result_available=False)
    executor = KubernetesJobExecutor(
        _task(),
        _tool_version(),
        execution_service=ExecutionService({"k8s_job": adapter}),
    )

    with pytest.raises(TaskExecutionError) as excinfo:
        await executor.execute()

    message = str(excinfo.value)
    # The message must explain what happened: an opaque "HTTP 404" leaves the
    # operator with nothing to act on.
    assert "消失" in message
    assert "404" not in message
    assert excinfo.value.details == {"external_id": "job-gone", "reason": "job_gone"}


@pytest.mark.asyncio
async def test_executor_still_fails_cleanly_on_a_cancelled_job():
    """Cancellation keeps working: the worker maps a failure to CANCELLED."""
    from app.execution.contracts import ExecutionHandleGone
    from app.execution.service import ExecutionService
    from app.tasks.executors.errors import TaskExecutionError
    from app.tasks.executors.kubernetes_job import KubernetesJobExecutor

    class CancelledAdapter(_VanishingAdapter):
        async def reconcile(self, execution_id):
            self.calls.append(("reconcile", execution_id))
            raise ExecutionHandleGone(f"Kubernetes Job no longer exists: {execution_id}")

    adapter = CancelledAdapter(result_available=False)
    task = _task()
    executor = KubernetesJobExecutor(
        task,
        _tool_version(),
        execution_service=ExecutionService({"k8s_job": adapter}),
    )

    with pytest.raises(TaskExecutionError):
        await executor.execute()

    # The executor records the external id before polling so the worker can
    # still reconcile the attempt after the Job is gone.
    assert task.extra_data["external_id"] == "job-gone"


@pytest.mark.asyncio
async def test_executor_does_not_treat_a_transport_error_as_a_vanished_job():
    """A real transport failure must keep propagating for the retry policy."""
    from app.execution.service import ExecutionService
    from app.tasks.executors.kubernetes_job import KubernetesJobExecutor

    class FlakyAdapter(_VanishingAdapter):
        async def reconcile(self, execution_id):
            self.calls.append(("reconcile", execution_id))
            raise RuntimeError("connection reset by peer")

    adapter = FlakyAdapter(result_available=True)
    executor = KubernetesJobExecutor(
        _task(),
        _tool_version(),
        execution_service=ExecutionService({"k8s_job": adapter}),
    )

    with pytest.raises(RuntimeError) as excinfo:
        await executor.execute()

    assert "connection reset" in str(excinfo.value)
    # Recovery must not kick in: only a vanished Job triggers it.
    assert [call[0] for call in adapter.calls] == ["submit", "reconcile"]
