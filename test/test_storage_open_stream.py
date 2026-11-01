"""存储后端 open_stream 流式读取测试（Task 3c §5.4）。"""

from __future__ import annotations

import pytest

from app.storage import local as local_module
from app.storage.local import LocalStorageBackend
from app.storage.minio_backend import MinIOStorageBackend


class _TrackingHandle:
    """包装真实文件句柄，记录 close 是否被调用。"""

    def __init__(self, path):
        self._handle = open(path, "rb")
        self.closed = False

    def read(self, size: int) -> bytes:
        return self._handle.read(size)

    def close(self) -> None:
        self.closed = True
        self._handle.close()


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0
        self.closed = False
        self.released = False

    def read(self, size: int) -> bytes:
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class _FakeMinioClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def get_object(self, bucket: str, path: str) -> _FakeResponse:
        return self._response


@pytest.mark.asyncio
async def test_local_open_stream_yields_all_chunks_and_closes(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "payload.bin"
    path.write_bytes(b"abcdefghij")

    handle = _TrackingHandle(path)
    monkeypatch.setattr(local_module, "_open_local", lambda _path: handle)

    storage = LocalStorageBackend(base_path=tmp_path)
    chunks = [chunk async for chunk in storage.open_stream(str(path), chunk_size=4)]

    assert b"".join(chunks) == b"abcdefghij"
    assert [len(chunk) for chunk in chunks] == [4, 4, 2]
    assert handle.closed is True


@pytest.mark.asyncio
async def test_minio_open_stream_reads_chunks_and_releases_response():
    response = _FakeResponse(b"0123456789")
    # 绕过 __init__ 的真实 Minio 客户端构造，只注入 get_object 假实现。
    storage = object.__new__(MinIOStorageBackend)
    storage.bucket = "bucket"
    storage.client = _FakeMinioClient(response)

    chunks = [chunk async for chunk in storage.open_stream("key", chunk_size=3)]

    assert b"".join(chunks) == b"0123456789"
    assert [len(chunk) for chunk in chunks] == [3, 3, 3, 1]
    assert response.closed is True
    assert response.released is True
