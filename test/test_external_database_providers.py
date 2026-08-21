"""External scientific database provider tests."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.external_databases import providers


@pytest.mark.asyncio
async def test_rcsb_provider_retries_read_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str):
            calls.append(url)
            if len(calls) == 1:
                raise httpx.ReadTimeout("slow RCSB response")
            return SimpleNamespace(status_code=200, content=b"HEADER TEST\nATOM      1\nEND\n")

    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeAsyncClient)

    payload = await providers.RCSBProvider().fetch_protein("1a2b")

    assert len(calls) == 2
    assert payload.name == "1A2B"
    assert payload.files[0].filename == "1A2B.pdb"
