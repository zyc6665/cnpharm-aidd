"""AIDD agent background reconciliation tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.background import AgentReconcileLoop  # noqa: E402


@pytest.mark.asyncio
async def test_agent_reconcile_loop_runs_until_stopped() -> None:
    calls = 0

    async def fake_reconcile():
        nonlocal calls
        calls += 1

    loop = AgentReconcileLoop(reconcile=fake_reconcile, interval_seconds=0.01)

    loop.start()
    await asyncio.sleep(0.035)
    await loop.stop()

    assert calls >= 1
    assert loop.is_running is False


@pytest.mark.asyncio
async def test_agent_reconcile_loop_start_is_idempotent() -> None:
    calls = 0

    async def fake_reconcile():
        nonlocal calls
        calls += 1

    loop = AgentReconcileLoop(reconcile=fake_reconcile, interval_seconds=0.01)

    loop.start()
    first_task = loop.task
    loop.start()
    await asyncio.sleep(0.02)
    await loop.stop()

    assert first_task is not None
    assert loop.task is first_task
    assert calls >= 1
