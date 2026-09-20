"""统一文件写入模块回归测试。"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_store_file_bytes_writes_storage_before_database_flush(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.files.writer import store_file_bytes

    storage_root = tmp_path / "storage"
    monkeypatch.setattr("app.files.storage_path.STORAGE_PATH", storage_root)

    class FakeSession:
        def __init__(self):
            self.records = []

        def add(self, record):
            self.records.append(record)

        async def flush(self):
            assert self.records[0].storage_path
            assert Path(self.records[0].storage_path).read_bytes() == b"payload"

    session = FakeSession()
    record = await store_file_bytes(
        session,
        content=b"payload",
        filename="result.json",
        content_type="application/json",
        owner_id="user-1",
        project_id="project-1",
        source_type="tool_output",
    )

    assert record.id == session.records[0].id
    assert record.storage_path
    assert Path(record.storage_path).name.endswith("_result.json")
    assert record.size_bytes == len(b"payload")
    assert record.project_id == "project-1"


@pytest.mark.asyncio
async def test_store_file_bytes_removes_storage_file_when_flush_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("app.files.storage_path.STORAGE_PATH", tmp_path / "storage")

    class FakeSession:
        def add(self, record):
            self.record = record

        async def flush(self):
            raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        from app.files.writer import store_file_bytes

        await store_file_bytes(
            FakeSession(),
            content=b"payload",
            filename="result.json",
            content_type="application/json",
            owner_id="user-1",
            project_id="project-1",
            source_type="tool_output",
        )

    assert not [path for path in (tmp_path / "storage").rglob("*") if path.is_file()]
