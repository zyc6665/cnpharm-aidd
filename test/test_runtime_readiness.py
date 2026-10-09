"""Runtime readiness checks for queue-backed execution."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from app.api.v1 import system


@pytest.mark.asyncio
async def test_celery_health_is_degraded_when_no_worker_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeInspector:
        def ping(self):
            return None

    class FakeControl:
        def inspect(self, *, timeout):
            assert timeout == 1.0
            return FakeInspector()

    fake_celery = SimpleNamespace(
        conf=SimpleNamespace(broker_url="redis://redis:6379/1"),
        control=FakeControl(),
    )
    celery_module = importlib.import_module("app.worker.celery_app")
    monkeypatch.setattr(celery_module, "celery_app", fake_celery)

    status = await system._check_celery()

    assert status.status == "degraded"
    assert status.message == "Celery broker 已配置，但没有活跃 Worker"


@pytest.mark.asyncio
async def test_celery_health_is_healthy_when_worker_responds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeInspector:
        def ping(self):
            return {"worker-1": {"ok": "pong"}}

    class FakeControl:
        def inspect(self, *, timeout):
            return FakeInspector()

    fake_celery = SimpleNamespace(
        conf=SimpleNamespace(broker_url="redis://redis:6379/1"),
        control=FakeControl(),
    )
    celery_module = importlib.import_module("app.worker.celery_app")
    monkeypatch.setattr(celery_module, "celery_app", fake_celery)

    status = await system._check_celery()

    assert status.status == "healthy"
    assert "活跃 Worker 数: 1" in status.message


def test_celery_runtime_uses_configured_timezone_and_task_limits() -> None:
    from app.config import settings
    from app.worker.celery_app import celery_app

    assert celery_app.conf.timezone == settings.CELERY_TIMEZONE
    assert celery_app.conf.task_soft_time_limit == settings.CELERY_TASK_SOFT_TIME_LIMIT
    assert celery_app.conf.task_time_limit == settings.CELERY_TASK_TIME_LIMIT


@pytest.mark.asyncio
async def test_minio_health_checks_bucket_connectivity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMinioBackend:
        bucket = "scitool-files"
        client = SimpleNamespace(bucket_exists=lambda bucket: bucket == "scitool-files")

    monkeypatch.setattr(system.settings, "STORAGE_BACKEND", "minio")
    monkeypatch.setattr(
        "app.storage.get_storage_backend",
        lambda: FakeMinioBackend(),
    )

    status = await system._check_storage()

    assert status.status == "healthy"
    assert status.message == "MinIO bucket 可访问 (scitool-files)"


@pytest.mark.asyncio
async def test_minio_health_reports_missing_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMinioBackend:
        bucket = "missing-bucket"
        client = SimpleNamespace(bucket_exists=lambda _bucket: False)

    monkeypatch.setattr(system.settings, "STORAGE_BACKEND", "minio")
    monkeypatch.setattr(
        "app.storage.get_storage_backend",
        lambda: FakeMinioBackend(),
    )

    status = await system._check_storage()

    assert status.status == "unhealthy"
    assert status.message == "MinIO bucket 不存在: missing-bucket"
