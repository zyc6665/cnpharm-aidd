"""Worker 与 API 的连接池形态必须分开。

背景：asyncpg 的异步连接**绑定创建它的事件循环**。Celery 的 threads / prefork 池里，
并发的两个任务可能各跑在自己的事件循环上；若共享同一个进程级连接池，第二个任务
会拿到「绑在别人循环上」的连接，报 `Future attached to a different loop`
（SQLAlchemy 会包装成 `MissingGreenlet` 或 `another operation is in progress`）。
因此 Worker 进程必须 `DB_POOL_MODE=null`（每会话新建连接），API 进程保持 `pooled`。
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.pool import NullPool

from app.database import session as session_module

ROOT = Path(__file__).resolve().parents[1]


def test_engine_uses_pool_by_default() -> None:
    assert session_module.engine.pool.__class__.__name__ != "NullPool"


def test_engine_switches_to_null_pool_when_configured(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "DB_POOL_MODE", "null")
    kwargs = session_module._engine_kwargs()

    assert kwargs["poolclass"] is NullPool
    # NullPool 下 pre_ping 只会多一次往返，关掉
    assert kwargs["pool_pre_ping"] is False


def test_compose_sets_null_pool_on_every_worker_service() -> None:
    compose = (ROOT / "deploy" / "compose" / "docker-compose.prod.yml").read_text(
        encoding="utf-8"
    )
    worker_blocks = [
        block.split("  depends_on:")[0]
        for block in compose.split("  celery-worker")[1:]
    ]

    assert worker_blocks, "未找到 celery-worker 服务定义"
    for block in worker_blocks:
        assert "DB_POOL_MODE: null" in block, f"Worker 服务缺少 DB_POOL_MODE: null\n{block[:200]}"
