"""Tests for storage-agnostic file content access."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.files.content import ensure_local_file, file_exists, read_file_bytes


@pytest.mark.asyncio
async def test_local_file_content_uses_persisted_path(tmp_path: Path) -> None:
    source = tmp_path / "source.pdb"
    source.write_bytes(b"ATOM\n")
    record = SimpleNamespace(
        id="file-local",
        filename="source.pdb",
        storage_backend="local",
        storage_path=str(source),
    )

    assert await file_exists(record) is True
    assert await read_file_bytes(record) == b"ATOM\n"

    destination = tmp_path / "materialized" / "source.pdb"
    assert await ensure_local_file(record, destination) == destination
    assert destination.read_bytes() == b"ATOM\n"


@pytest.mark.asyncio
async def test_minio_file_content_is_downloaded_before_local_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStorage:
        async def exists(self, path: str) -> bool:
            assert path == "inputs/files/file-remote/source.pdb"
            return True

        async def download(self, path: str) -> bytes:
            assert path == "inputs/files/file-remote/source.pdb"
            return b"ATOM\n"

    monkeypatch.setattr(
        "app.files.content.get_storage_backend",
        lambda backend: FakeStorage(),
    )
    record = SimpleNamespace(
        id="file-remote",
        filename="source.pdb",
        storage_backend="minio",
        storage_path="inputs/files/file-remote/source.pdb",
    )

    assert await file_exists(record) is True
    assert await read_file_bytes(record) == b"ATOM\n"

    destination = tmp_path / "materialized" / "source.pdb"
    assert await ensure_local_file(record, destination) == destination
    assert destination.read_bytes() == b"ATOM\n"
