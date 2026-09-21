"""Worker capability 配置加载测试。"""

import json

from app.config import settings
from app.tasks.worker_capability import load_worker_capability
from app.worker import tasks as worker_tasks


def test_load_worker_capability_from_json(monkeypatch) -> None:
    payload = {
        "worker_id": "gpu-worker-1",
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
    assert capability.executor_types == ("docker_image",)
    assert capability.gpu_memory_mb == 24576


def test_load_worker_capability_returns_none_when_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WORKER_CAPABILITY_JSON", None, raising=False)

    assert load_worker_capability() is None


def test_celery_registers_worker_capability_heartbeat_task() -> None:
    assert worker_tasks.heartbeat_worker_capability.name == (
        "app.worker.tasks.heartbeat_worker_capability"
    )
