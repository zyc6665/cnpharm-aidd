"""资源准入策略测试。"""

from app.tasks.resource_admission import (
    ResourceAdmissionPolicy,
    WorkerCapability,
)
from app.tasks.resource_profile import ResourceRequest


def _request(**overrides) -> ResourceRequest:
    values = {
        "executor_type": "docker_image",
        "tier": "heavy",
        "cpu": 8.0,
        "memory_gb": 32.0,
        "cpu_limit": 8.0,
        "memory_limit": "32g",
        "gpu_required": True,
        "gpu_count": 1,
        "gpu_memory_mb": 8192,
        "timeout_sec": 3600,
        "parallelism": 1,
    }
    values.update(overrides)
    return ResourceRequest(**values)


def _capability(**overrides) -> WorkerCapability:
    values = {
        "worker_id": "gpu-worker-1",
        "executor_types": ("docker_image", "python_script"),
        "tiers": ("medium", "heavy"),
        "cpu_capacity": 16.0,
        "memory_capacity_gb": 64.0,
        "gpu_count": 2,
        "gpu_memory_mb": 16384,
        "parallelism": 2,
        "healthy": True,
    }
    values.update(overrides)
    return WorkerCapability(**values)


def test_admission_accepts_request_that_fits_worker_capability() -> None:
    decision = ResourceAdmissionPolicy.evaluate(
        _request(),
        _capability(queue="gpu-worker-queue"),
    )

    assert decision.admitted is True
    assert decision.worker_id == "gpu-worker-1"
    assert decision.reason is None
    assert decision.queue == "gpu-worker-queue"


def test_admission_rejects_gpu_memory_shortage() -> None:
    decision = ResourceAdmissionPolicy.evaluate(
        _request(gpu_memory_mb=24576),
        _capability(gpu_memory_mb=16384),
    )

    assert decision.admitted is False
    assert decision.reason == "gpu_memory_insufficient"


def test_admission_rejects_unsupported_executor_before_capacity_checks() -> None:
    decision = ResourceAdmissionPolicy.evaluate(
        _request(executor_type="slurm_job"),
        _capability(cpu_capacity=1.0),
    )

    assert decision.admitted is False
    assert decision.reason == "executor_unsupported"


def test_admission_allows_unknown_capacity_in_non_strict_mode() -> None:
    decision = ResourceAdmissionPolicy.evaluate(
        _request(),
        WorkerCapability(worker_id="unregistered-worker"),
    )

    assert decision.admitted is True
    assert decision.worker_id == "unregistered-worker"


def test_admission_rejects_unhealthy_worker() -> None:
    decision = ResourceAdmissionPolicy.evaluate(
        _request(),
        _capability(healthy=False),
    )

    assert decision.admitted is False
    assert decision.reason == "worker_unhealthy"


def test_select_worker_returns_first_capable_worker() -> None:
    decision = ResourceAdmissionPolicy.select_worker(
        _request(),
        [
            _capability(worker_id="cpu-worker", gpu_count=0),
            _capability(worker_id="gpu-worker"),
        ],
    )

    assert decision.admitted is True
    assert decision.worker_id == "gpu-worker"


def test_select_worker_reports_no_capable_worker() -> None:
    decision = ResourceAdmissionPolicy.select_worker(
        _request(gpu_memory_mb=32768),
        [_capability(gpu_memory_mb=16384)],
    )

    assert decision.admitted is False
    assert decision.worker_id == ""
    assert decision.reason == "no_capable_worker"
