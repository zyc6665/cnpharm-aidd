"""健康检查在「服务忙」与「服务抖」下的判定。

两个真实故障（2026-11-12）：
1. Celery Worker 用 solo 池跑一条长任务时无法应答 ping，健康检查把「忙」报成
   「没有活跃 Worker」，界面出现「任务队列 降级」，但任务其实在正常运行。
2. Redis 偶发一次超时就把「缓存」翻红，刷新一下又好了——单次抖动不该算故障。
"""

import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.api.v1 import system as system_module  # noqa: E402
from app.common.time import utcnow  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.models.tasks import Task, TaskLog, TaskStatus  # noqa: E402
from app.worker import health as health_module  # noqa: E402


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_probe_state():
    system_module.reset_health_probe_state_for_tests()
    yield
    system_module.reset_health_probe_state_for_tests()


def _patch_worker_ping(monkeypatch: pytest.MonkeyPatch, workers: tuple[str, ...]) -> None:
    monkeypatch.setattr(
        health_module, "_effective_broker_url", lambda: "redis://localhost:6379/0"
    )
    monkeypatch.setattr(health_module, "_ping_workers_sync", lambda _timeout: workers)


async def _seed_running_task(
    session_factory: async_sessionmaker,
    *,
    log_age_seconds: float | None,
) -> str:
    task_id = str(uuid.uuid4())
    async with session_factory() as session:
        session.add(
            Task(
                id=task_id,
                user_id=None,
                project_id=None,
                tool_id=str(uuid.uuid4()),
                tool_version_id=str(uuid.uuid4()),
                name="分子生成",
                status=TaskStatus.RUNNING.value,
            )
        )
        if log_age_seconds is not None:
            session.add(
                TaskLog(
                    task_id=task_id,
                    timestamp=utcnow() - timedelta(seconds=log_age_seconds),
                    level="info",
                    message="[Pool] Queue 300",
                    log_data={"source": "runtime"},
                )
            )
        await session.commit()
    return task_id


@pytest.mark.asyncio
async def test_busy_worker_is_reported_healthy_while_writing_logs(
    monkeypatch, session_factory
):
    """ping 无人应答，但运行中任务的日志还在写 → Worker 活着，只是忙。"""
    _patch_worker_ping(monkeypatch, ())
    await _seed_running_task(session_factory, log_age_seconds=5)

    async with session_factory() as session:
        status = await system_module._check_celery(session)

    assert status.status == "healthy"
    assert "正在执行任务" in status.message


@pytest.mark.asyncio
async def test_worker_without_fresh_logs_is_degraded(monkeypatch, session_factory):
    """既 ping 不到、也没有新鲜的运行日志 → 仍要报降级（不能把真故障藏起来）。"""
    _patch_worker_ping(monkeypatch, ())
    await _seed_running_task(session_factory, log_age_seconds=3600)

    async with session_factory() as session:
        status = await system_module._check_celery(session)

    assert status.status == "degraded"
    assert "没有活跃 Worker" in status.message


@pytest.mark.asyncio
async def test_worker_ping_success_ignores_logs(monkeypatch, session_factory):
    _patch_worker_ping(monkeypatch, ("worker@host",))

    async with session_factory() as session:
        status = await system_module._check_celery(session)

    assert status.status == "healthy"
    assert "活跃 Worker 数: 1" in status.message


def _patch_cache(monkeypatch: pytest.MonkeyPatch, *, ok: bool) -> None:
    class _Cache:
        async def set(self, key, value, expire=None):
            if not ok:
                raise RuntimeError("Timeout reading from socket")

        async def get(self, key):
            return "ok" if ok else None

        async def delete(self, key):
            return None

    import app.cache as cache_module

    monkeypatch.setattr(cache_module, "get_cache_backend", lambda: _Cache())


@pytest.mark.asyncio
async def test_cache_single_failure_is_debounced(monkeypatch):
    _patch_cache(monkeypatch, ok=False)

    first = await system_module._check_cache()
    assert first.status == "healthy"
    assert "未达判定阈值" in first.message

    second = await system_module._check_cache()
    assert second.status == "unhealthy"
    assert "缓存服务异常" in second.message


@pytest.mark.asyncio
async def test_cache_success_clears_failure_streak(monkeypatch):
    _patch_cache(monkeypatch, ok=False)
    await system_module._check_cache()

    _patch_cache(monkeypatch, ok=True)
    recovered = await system_module._check_cache()
    assert recovered.status == "healthy"
    assert "缓存服务正常" in recovered.message

    # 失败计数已清零：再抖一次仍然只算第一次，不立刻翻红。
    _patch_cache(monkeypatch, ok=False)
    transient = await system_module._check_cache()
    assert transient.status == "healthy"
    assert "未达判定阈值" in transient.message
