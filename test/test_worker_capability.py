"""Worker capability 配置加载测试。"""

import json

from app.config import settings
from app.tasks.worker_capability import (
    load_worker_capability,
    validate_worker_queue_contract,
)
from app.worker import tasks as worker_tasks


def test_load_worker_capability_from_json(monkeypatch) -> None:
    payload = {
        "worker_id": "gpu-worker-1",
        "queue": "gpu-worker-queue",
        "executor_types": ["docker_image"],
        "tiers": ["heavy"],
        "cpu_capacity": 16,
        "memory_capacity_gb": 64,
        "gpu_count": 2,
        "gpu_memory_mb": 24576,
        "parallelism": 2,
        "healthy": True,
    }
    monkeypatch.setattr(
        settings,
        "WORKER_CAPABILITY_JSON",
        json.dumps(payload),
        raising=False,
    )

    capability = load_worker_capability()

    assert capability is not None
    assert capability.worker_id == "gpu-worker-1"
    assert capability.queue == "gpu-worker-queue"
    assert capability.executor_types == ("docker_image",)
    assert capability.gpu_memory_mb == 24576


def test_load_worker_capability_returns_none_when_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_JSON", None, raising=False)

    assert load_worker_capability() is None


def test_worker_queue_contract_requires_declared_queue_to_be_listened(
    monkeypatch,
) -> None:
    capability_payload = {
        "worker_id": "gpu-worker-1",
        "queue": "gpu-worker-queue",
    }
    monkeypatch.setattr(
        settings,
        "WORKER_CAPABILITY_JSON",
        json.dumps(capability_payload),
        raising=False,
    )
    capability = load_worker_capability()

    assert capability is not None
    assert validate_worker_queue_contract(capability, "cpu_queue") == (
        False,
        "worker_queue_not_listened",
    )
    assert validate_worker_queue_contract(capability, "gpu-worker-queue") == (
        True,
        None,
    )
    assert validate_worker_queue_contract(capability, None) == (True, None)


def test_worker_capability_heartbeat_skips_invalid_queue_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "WORKER_CAPABILITY_JSON",
        json.dumps({"worker_id": "gpu-worker-1", "queue": "gpu-worker-queue"}),
        raising=False,
    )
    monkeypatch.setattr(settings, "WORKER_LISTEN_QUEUES", "gpu_queue", raising=False)

    async def fail_register(_capability):
        raise AssertionError("invalid queue capability must not register")

    monkeypatch.setattr(worker_tasks, "_register_worker_capability_impl", fail_register)

    result = worker_tasks.heartbeat_worker_capability()

    assert result == {
        "registered": False,
        "worker_id": "gpu-worker-1",
        "reason": "worker_queue_not_listened",
    }


def test_load_worker_capability_expands_container_hostname(monkeypatch) -> None:
    monkeypatch.setenv("HOSTNAME", "container-123")
    monkeypatch.setattr(
        settings,
        "WORKER_CAPABILITY_JSON",
        json.dumps({"worker_id": "scitool-default-${HOSTNAME}"}),
        raising=False,
    )

    capability = load_worker_capability()

    assert capability is not None
    assert capability.worker_id == "scitool-default-container-123"


def test_celery_heartbeat_schedule_targets_configured_queues(monkeypatch) -> None:
    from app.worker.celery_app import create_celery_app

    monkeypatch.setattr(
        settings,
        "WORKER_CAPABILITY_HEARTBEAT_QUEUES",
        "default,heavy_compute,gpu_queue",
        raising=False,
    )
    app = create_celery_app()
    schedule = app.conf.beat_schedule

    assert schedule["heartbeat-worker-capability-default"]["options"] == {"queue": "default"}
    assert schedule["heartbeat-worker-capability-heavy_compute"]["options"] == {"queue": "heavy_compute"}
    assert schedule["heartbeat-worker-capability-gpu_queue"]["options"] == {"queue": "gpu_queue"}
    assert schedule["reclaim-stale-cancellations"] == {
        "task": "app.worker.tasks.reclaim_stale_cancellations",
        "schedule": 60.0,
    }


def test_celery_registers_worker_capability_heartbeat_task() -> None:
    assert worker_tasks.heartbeat_worker_capability.name == (
        "app.worker.tasks.heartbeat_worker_capability"
    )


def test_celery_worker_heartbeat_signal_refreshes_own_capability(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "WORKER_CAPABILITY_JSON",
        json.dumps({"worker_id": "worker-signal-1", "queue": "tool_tasks"}),
        raising=False,
    )
    monkeypatch.setattr(settings, "WORKER_LISTEN_QUEUES", "tool_tasks", raising=False)
    registered = []

    async def fake_register(capability):
        registered.append(capability.worker_id)

    monkeypatch.setattr(worker_tasks, "_register_worker_capability_impl", fake_register)

    result = worker_tasks.on_celery_heartbeat_sent(sender="worker-1")

    assert result == {"registered": True, "worker_id": "worker-signal-1"}
    assert registered == ["worker-signal-1"]


def test_celery_worker_heartbeat_signal_is_throttled(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "WORKER_CAPABILITY_JSON",
        json.dumps({"worker_id": "worker-signal-2", "queue": "tool_tasks"}),
        raising=False,
    )
    monkeypatch.setattr(settings, "WORKER_LISTEN_QUEUES", "tool_tasks", raising=False)
    registered = []
    clock = iter((100.0, 110.0, 140.0))

    async def fake_register(capability):
        registered.append(capability.worker_id)

    monkeypatch.setattr(worker_tasks, "_register_worker_capability_impl", fake_register)
    monkeypatch.setattr(worker_tasks, "_capability_signal_now", lambda: next(clock))
    worker_tasks._capability_signal_last_refresh.clear()

    first = worker_tasks.on_celery_heartbeat_sent(sender="worker-2")
    second = worker_tasks.on_celery_heartbeat_sent(sender="worker-2")
    third = worker_tasks.on_celery_heartbeat_sent(sender="worker-2")

    assert first["registered"] is True
    assert second == {"registered": False, "worker_id": "worker-signal-2", "skipped": "throttled"}
    assert third["registered"] is True
    assert registered == ["worker-signal-2", "worker-signal-2"]
