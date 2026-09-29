
from __future__ import annotations

import asyncio

import pytest

from app.services import workflow_reconciliation


@pytest.mark.asyncio
async def test_reconcile_skips_when_distributed_lock_is_busy(monkeypatch):
    class BusyCache:
        async def set(self, key, value, *, nx=False, ex=None, expire=None):
            assert nx is True
            return False

    monkeypatch.setattr(workflow_reconciliation, "get_cache", lambda: BusyCache())

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("workflow reconciliation must not run without the lock")

    monkeypatch.setattr(
        workflow_reconciliation,
        "reconcile_waiting_workflow_runs",
        fail_if_called,
    )

    assert await workflow_reconciliation.reconcile_all_waiting_workflow_runs() == 0


@pytest.mark.asyncio
async def test_reconcile_releases_lock_after_failure(monkeypatch):
    class TrackingCache:
        def __init__(self):
            self.deleted = []

        async def set(self, key, value, *, nx=False, ex=None, expire=None):
            return True

        async def delete_if_value(self, key, value):
            self.deleted.append((key, value))
            return True

    cache = TrackingCache()
    monkeypatch.setattr(workflow_reconciliation, "get_cache", lambda: cache)

    class SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(
        workflow_reconciliation,
        "async_session_factory",
        lambda: SessionContext(),
    )

    async def fail_reconcile(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        workflow_reconciliation,
        "reconcile_waiting_workflow_runs",
        fail_reconcile,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await workflow_reconciliation.reconcile_all_waiting_workflow_runs()

    assert len(cache.deleted) == 1


@pytest.mark.asyncio
async def test_reconcile_stops_when_lock_renewal_is_lost(monkeypatch):
    class LostCache:
        def __init__(self):
            self.deleted = []

        async def set(self, key, value, *, nx=False, ex=None, expire=None):
            return True

        async def expire_if_value(self, key, value, seconds):
            return False

        async def delete_if_value(self, key, value):
            self.deleted.append((key, value))
            return True

    cache = LostCache()
    monkeypatch.setattr(workflow_reconciliation, "get_cache", lambda: cache)
    monkeypatch.setattr(
        workflow_reconciliation.settings,
        "WORKFLOW_RECONCILE_LOCK_TTL_SECONDS",
        1,
    )

    stopped = False

    async def blocked_reconcile(*args, **kwargs):
        nonlocal stopped
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            stopped = True
            raise

    monkeypatch.setattr(
        workflow_reconciliation,
        "reconcile_waiting_workflow_runs",
        blocked_reconcile,
    )

    with pytest.raises(RuntimeError, match="lock was lost"):
        await workflow_reconciliation.reconcile_all_waiting_workflow_runs()

    assert stopped is True
    assert len(cache.deleted) == 1
