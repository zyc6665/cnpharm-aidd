"""MinIO 存储后端行为测试。"""

import logging
import sys
import types
from types import SimpleNamespace

import pytest


class _FakeMinioModule(types.ModuleType):
    def __init__(self):
        super().__init__("minio")
        self.next_client = None

    def Minio(self, *args, **kwargs):
        return self.next_client


class _FakeMinioClient:
    def __init__(self):
        self.removed = []

    def bucket_exists(self, bucket: str) -> bool:
        return True

    def get_object(self, bucket: str, path: str):
        return _FakeMinioResponse()

    def remove_object(self, bucket: str, path: str) -> None:
        self.removed.append((bucket, path))

    def stat_object(self, bucket: str, path: str):
        return SimpleNamespace(size=3, content_type="text/plain", etag="etag-1")


class _FakeMinioResponse:
    def read(self) -> bytes:
        return b"ok"

    def close(self) -> None:
        raise RuntimeError("close failed")

    def release_conn(self) -> None:
        raise RuntimeError("release failed")


@pytest.fixture()
def fake_minio(monkeypatch):
    module = _FakeMinioModule()
    client = _FakeMinioClient()
    module.next_client = client
    monkeypatch.setitem(sys.modules, "minio", module)
    return client


@pytest.mark.asyncio
async def test_download_keeps_payload_when_response_cleanup_fails(fake_minio, caplog):
    from app.storage.minio_backend import MinIOStorageBackend

    backend = MinIOStorageBackend(
        endpoint="minio.local:9000",
        access_key="access",
        secret_key="secret",
        bucket="bucket",
    )

    with caplog.at_level(logging.WARNING, logger="app.storage.minio_backend"):
        assert await backend.download("foo.txt") == b"ok"

    assert "Failed to close MinIO response for bucket/foo.txt" in caplog.text
    assert "Failed to release MinIO response connection for bucket/foo.txt" in caplog.text


@pytest.mark.asyncio
async def test_delete_logs_failure_and_returns_false(fake_minio, caplog):
    from app.storage.minio_backend import MinIOStorageBackend

    backend = MinIOStorageBackend(
        endpoint="minio.local:9000",
        access_key="access",
        secret_key="secret",
        bucket="bucket",
    )
    fake_minio.remove_object = lambda bucket, path: (_ for _ in ()).throw(
        RuntimeError("delete failed")
    )

    with caplog.at_level(logging.WARNING, logger="app.storage.minio_backend"):
        assert await backend.delete("foo.txt") is False

    assert "Failed to delete MinIO object bucket/foo.txt" in caplog.text
