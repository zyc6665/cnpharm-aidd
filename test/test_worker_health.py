"""Celery Worker 可用性探测的用例。

守护的是一条真实事故路径：`CELERY_BROKER_URL` 配了、Worker 没起，
任务永远停在「排队中」且日志里没有任何报错。探测必须做到：
无 Broker 时明确「不适用」、有 Broker 没 Worker 时明确「不可用」、
探测本身出错也不能影响主流程。
"""

import pytest

from app.api.v1 import system as system_module
from app.config import settings
from app.worker import health as health_module
from app.worker.health import (
    WorkerAvailability,
    probe_workers,
    reset_worker_availability_cache,
    worker_availability,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_worker_availability_cache()
    yield
    reset_worker_availability_cache()


@pytest.mark.asyncio
async def test_probe_reports_unconfigured_without_broker(monkeypatch):
    # Broker 有两个来源（settings 与 celery_app.conf），两处都空才算没配。
    # 直接钉住「实际生效地址」的解析结果，避免测试依赖本机 .env。
    monkeypatch.setattr(health_module, "_effective_broker_url", lambda: "")

    result = await probe_workers()

    assert result.configured is False
    assert result.available is False
    assert "direct" in result.describe()


@pytest.mark.asyncio
async def test_probe_reports_workers_from_ping(monkeypatch):
    monkeypatch.setattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(
        health_module,
        "_ping_workers_sync",
        lambda _timeout: ("worker-b@host", "worker-a@host"),
    )

    result = await probe_workers()

    assert result.configured is True
    assert result.available is True
    assert set(result.workers) == {"worker-a@host", "worker-b@host"}
    assert "worker-a@host" in result.describe()


@pytest.mark.asyncio
async def test_probe_swallows_broker_errors(monkeypatch):
    monkeypatch.setattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")

    def _boom(_timeout):
        raise RuntimeError("broker unreachable")

    monkeypatch.setattr(health_module, "_ping_workers_sync", _boom)

    result = await probe_workers()

    assert result.configured is True
    assert result.available is False
    assert "没有 Worker 响应" in result.describe()


@pytest.mark.asyncio
async def test_worker_availability_caches_until_expiry(monkeypatch):
    monkeypatch.setattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(settings, "CELERY_WORKER_PROBE_CACHE_SECONDS", 60.0)
    calls: list[float] = []

    def _count(timeout):
        calls.append(timeout)
        return ("worker@host",)

    monkeypatch.setattr(health_module, "_ping_workers_sync", _count)

    first = await worker_availability()
    second = await worker_availability()

    assert first.workers == ("worker@host",)
    assert second is first
    assert len(calls) == 1

    refreshed = await worker_availability(refresh=True)

    assert refreshed.workers == ("worker@host",)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_worker_availability_does_not_cache_when_disabled(monkeypatch):
    monkeypatch.setattr(health_module, "_effective_broker_url", lambda: "")

    first = await worker_availability()
    second = await worker_availability()

    assert first.configured is False
    assert first.workers == ()
    assert second.workers == ()


@pytest.mark.asyncio
async def test_health_check_degrades_when_no_worker(monkeypatch):
    monkeypatch.setattr(
        health_module, "_effective_broker_url", lambda: "redis://localhost:6379/0"
    )
    monkeypatch.setattr(health_module, "_ping_workers_sync", lambda _timeout: ())

    status = await system_module._check_celery()

    assert status.status == "degraded"
    assert "没有活跃 Worker" in status.message


@pytest.mark.asyncio
async def test_health_check_is_healthy_with_worker(monkeypatch):
    monkeypatch.setattr(
        health_module, "_effective_broker_url", lambda: "redis://localhost:6379/0"
    )
    monkeypatch.setattr(
        health_module, "_ping_workers_sync", lambda _timeout: ("worker@host",)
    )

    status = await system_module._check_celery()

    assert status.status == "healthy"
    assert "活跃 Worker 数: 1" in status.message


@pytest.mark.asyncio
async def test_health_check_is_unhealthy_without_broker(monkeypatch):
    monkeypatch.setattr(health_module, "_effective_broker_url", lambda: "")

    status = await system_module._check_celery()

    assert status.status == "unhealthy"
    assert "未配置" in status.message


def test_worker_registers_executor_gateway_for_both_pool_events() -> None:
    """执行器网关必须在 `prefork` 与 `threads` 两种池下都被注册。

    `worker_process_init` 只在 prefork 子进程里触发；`threads` 池不触发它。
    只挂前者时，Worker 的执行器表是空的，提交任务会报「不支持的执行器类型: k8s_job」。
    """
    from celery.signals import worker_process_init, worker_ready

    # 注意 `app/worker/__init__.py` 把 `celery_app` 这个名字导出成了 Celery 实例，
    # 所以 `import app.worker.celery_app as m` 拿到的是实例而不是模块。
    import importlib

    celery_module = importlib.import_module("app.worker.celery_app")

    # Celery 的 Signal.receivers 是 (lookup_key, receiver) 二元组列表，
    # 而 receiver 可能是 weakref，需要解引用后才能与函数对象比较。
    def _resolve(signal) -> set:
        resolved = set()
        for _key, receiver in signal.receivers:
            target = receiver() if isinstance(receiver, weakref.ref) else receiver
            if target is not None:
                resolved.add(target)
        return resolved

    import weakref

    init_receivers = _resolve(worker_process_init)
    ready_receivers = _resolve(worker_ready)

    assert celery_module._configure_managed_execution_runtime_on_worker_start in init_receivers
    assert celery_module._configure_managed_execution_runtime_on_worker_ready in ready_receivers
