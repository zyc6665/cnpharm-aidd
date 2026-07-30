"""异步 coroutine 在同步入口中的运行兼容性测试。"""

from __future__ import annotations

import pytest

from app.common.async_runtime import run_coro_sync


async def _sample(value: str) -> str:
    return value


def test_run_coro_sync_runs_without_existing_event_loop() -> None:
    assert run_coro_sync(_sample("sync")) == "sync"


@pytest.mark.asyncio
async def test_run_coro_sync_runs_inside_existing_event_loop() -> None:
    assert run_coro_sync(_sample("async")) == "async"
