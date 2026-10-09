"""MinIO adapter behavior tests without a live object store."""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from app.storage.minio_backend import MinIOStorageBackend


class MinIOError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _backend(monkeypatch: pytest.MonkeyPatch) -> MinIOStorageBackend:
    monkeypatch.setattr("app.config.settings.MINIO_SECURE", True)
    backend = MinIOStorageBackend(secure=False)
    backend.client = SimpleNamespace()
    return backend


@pytest.mark.asyncio
async def test_minio_constructor_does_not_make_network_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend(monkeypatch)

    assert backend.secure is False


@pytest.mark.asyncio
async def test_minio_io_runs_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _backend(monkeypatch)
    started = threading.Event()

    def slow_stat(_bucket: str, _path: str) -> object:
        started.set()
        time.sleep(0.05)
        return object()

    backend.client.stat_object = slow_stat
    check_task = asyncio.create_task(backend.exists("inputs/test.pdb"))
    await asyncio.sleep(0)

    assert started.is_set()
    assert not check_task.done()
    assert await check_task is True


@pytest.mark.asyncio
async def test_exists_only_swallows_missing_object_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend(monkeypatch)

    def missing(_bucket: str, _path: str) -> None:
        raise MinIOError("NoSuchKey")

    backend.client.stat_object = missing
    assert await backend.exists("missing.pdb") is False

    def denied(_bucket: str, _path: str) -> None:
        raise MinIOError("AccessDenied")

    backend.client.stat_object = denied
    with pytest.raises(MinIOError, match="AccessDenied"):
        await backend.exists("private.pdb")


@pytest.mark.asyncio
async def test_get_info_only_returns_none_for_missing_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend(monkeypatch)

    def missing(_bucket: str, _path: str) -> None:
        raise MinIOError("NoSuchObject")

    backend.client.stat_object = missing
    assert await backend.get_info("missing.pdb") is None

    def denied(_bucket: str, _path: str) -> None:
        raise MinIOError("AccessDenied")

    backend.client.stat_object = denied
    with pytest.raises(MinIOError, match="AccessDenied"):
        await backend.get_info("private.pdb")


@pytest.mark.asyncio
async def test_download_closes_response_after_read(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _backend(monkeypatch)
    response = SimpleNamespace(
        read=lambda: b"ATOM\n",
        close=lambda: setattr(response, "closed", True),
        release_conn=lambda: setattr(response, "released", True),
        closed=False,
        released=False,
    )
    backend.client.get_object = lambda _bucket, _path: response

    assert await backend.download("protein.pdb") == b"ATOM\n"
    assert response.closed is True
    assert response.released is True
