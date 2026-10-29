"""Kubernetes object-storage artifact collection contract tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig
from app.execution.transports.kubernetes_artifacts import (
    KubernetesArtifactCollectionError,
    KubernetesArtifactCollector,
    KubernetesObjectStorageConfig,
)


class FakeObjectStorage:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.streamed: list[str] = []

    async def download(self, path: str) -> bytes:
        if path not in self.objects:
            raise FileNotFoundError(path)
        return self.objects[path]

    def open_stream(self, path: str, chunk_size: int = 1024 * 1024):
        if path not in self.objects:
            raise FileNotFoundError(path)
        payload = self.objects[path]
        self.streamed.append(path)

        async def _iter():
            for offset in range(0, len(payload), chunk_size):
                yield payload[offset : offset + chunk_size]

        return _iter()


def _config() -> KubernetesJobExecutionConfig:
    return KubernetesJobExecutionConfig(
        cluster_alias="platform",
        namespace="model-jobs",
        credential_ref="platform-k8s",
        service_account="model-runner",
    )


def _result_payload(output_sha: str) -> bytes:
    return json.dumps(
        {
            "result_version": "aidd.sciminer/result",
            "artifacts": {
                "report": {
                    "type": "run_report@1",
                    "files": {
                        "report": {
                            "path": "reports/result.json",
                            "sha256": output_sha,
                            "content_type": "application/json",
                        }
                    },
                }
            },
        }
    ).encode("utf-8")


@pytest.mark.asyncio
async def test_collector_downloads_result_and_output_files(tmp_path: Path):
    output = b'{"status":"ok"}'
    storage = FakeObjectStorage(
        {
            "executions/model-jobs/sciminer-job-1/result.json": _result_payload(
                hashlib.sha256(output).hexdigest()
            ),
            "executions/model-jobs/sciminer-job-1/reports/result.json": output,
        }
    )
    collector = KubernetesArtifactCollector(
        storage,
        storage_config=KubernetesObjectStorageConfig(output_prefix="executions"),
        staging_root=tmp_path,
    )

    collection = await collector.collect(
        "model-jobs/sciminer-job-1",
        _config(),
    )

    assert collection.result_payload["result_version"] == "aidd.sciminer/result"
    assert collection.artifacts[0].path == "reports/result.json"
    assert collection.artifacts[0].artifact_type == "run_report@1"
    assert collection.artifacts[0].sha256 == hashlib.sha256(output).hexdigest()
    assert (collection.source_root / "reports/result.json").read_bytes() == output


@pytest.mark.asyncio
async def test_collector_rejects_output_checksum_mismatch(tmp_path: Path):
    output = b"actual"
    storage = FakeObjectStorage(
        {
            "executions/model-jobs/job-1/result.json": _result_payload("0" * 64),
            "executions/model-jobs/job-1/reports/result.json": output,
        }
    )
    collector = KubernetesArtifactCollector(
        storage,
        storage_config=KubernetesObjectStorageConfig(output_prefix="executions"),
        staging_root=tmp_path,
    )

    with pytest.raises(KubernetesArtifactCollectionError, match="checksum"):
        await collector.collect("model-jobs/job-1", _config())


@pytest.mark.asyncio
async def test_collector_rejects_unsafe_result_path(tmp_path: Path):
    result = json.dumps(
        {
            "result_version": "aidd.sciminer/result",
            "artifacts": {
                "report": {
                    "type": "run_report@1",
                    "files": {
                        "report": {
                            "path": "../escape.json",
                            "sha256": "0" * 64,
                        }
                    },
                }
            },
        }
    ).encode("utf-8")
    storage = FakeObjectStorage(
        {"executions/model-jobs/job-1/result.json": result}
    )
    collector = KubernetesArtifactCollector(
        storage,
        storage_config=KubernetesObjectStorageConfig(output_prefix="executions"),
        staging_root=tmp_path,
    )

    with pytest.raises(KubernetesArtifactCollectionError, match="Unsafe output path"):
        await collector.collect("model-jobs/job-1", _config())


@pytest.mark.asyncio
async def test_collector_rejects_cross_namespace_external_id(tmp_path: Path):
    collector = KubernetesArtifactCollector(
        FakeObjectStorage({}),
        storage_config=KubernetesObjectStorageConfig(output_prefix="executions"),
        staging_root=tmp_path,
    )

    with pytest.raises(KubernetesArtifactCollectionError, match="namespace"):
        await collector.collect("other-namespace/job-1", _config())


@pytest.mark.asyncio
async def test_collector_streams_large_output_without_buffering_whole_file(tmp_path: Path):
    # 3MB 产物，按 1MB 分块即可验证「边下边算边写」而不是整块读入。
    output = bytes(range(256)) * (3 * 1024 * 1024 // 256)
    output_sha = hashlib.sha256(output).hexdigest()
    storage = FakeObjectStorage(
        {
            "executions/model-jobs/job-big/result.json": _result_payload(output_sha),
            "executions/model-jobs/job-big/reports/result.json": output,
        }
    )
    collector = KubernetesArtifactCollector(
        storage,
        storage_config=KubernetesObjectStorageConfig(output_prefix="executions"),
        staging_root=tmp_path,
    )

    collection = await collector.collect("model-jobs/job-big", _config())

    written = (collection.source_root / "reports/result.json").read_bytes()
    assert written == output
    assert collection.artifacts[0].sha256 == output_sha
    # 输出对象走流式通道（open_stream），而不是 download 整块读入。
    assert "executions/model-jobs/job-big/reports/result.json" in storage.streamed
    assert not (tmp_path / "model-jobs" / "job-big" / "output" / "reports" / "result.json.part").exists()


@pytest.mark.asyncio
async def test_collector_stream_failure_is_not_silent(tmp_path: Path):
    class FailingStreamStorage(FakeObjectStorage):
        def open_stream(self, path: str, chunk_size: int = 1024 * 1024):
            async def _iter():
                yield b"partial"
                raise OSError("connection reset")

            return _iter()

    output = b"whatever"
    storage = FailingStreamStorage(
        {
            "executions/model-jobs/job-err/result.json": _result_payload(
                hashlib.sha256(output).hexdigest()
            ),
            "executions/model-jobs/job-err/reports/result.json": output,
        }
    )
    collector = KubernetesArtifactCollector(
        storage,
        storage_config=KubernetesObjectStorageConfig(output_prefix="executions"),
        staging_root=tmp_path,
    )

    with pytest.raises(KubernetesArtifactCollectionError, match="failed to download"):
        await collector.collect("model-jobs/job-err", _config())

    output_dir = tmp_path / "model-jobs" / "job-err" / "output" / "reports"
    assert not (output_dir / "result.json").exists()
    assert not (output_dir / "result.json.part").exists()


@pytest.mark.asyncio
async def test_collector_stream_open_failure_leaves_no_part_file(tmp_path: Path):
    # 输出对象不存在：open_stream 一被调用就抛异常（不是迭代到一半才抛）。
    # 失败路径必须删掉已创建的 .part 临时文件，不能在磁盘上留半截产物。
    output = b"whatever"
    storage = FakeObjectStorage(
        {
            "executions/model-jobs/job-open/result.json": _result_payload(
                hashlib.sha256(output).hexdigest()
            )
        }
    )
    collector = KubernetesArtifactCollector(
        storage,
        storage_config=KubernetesObjectStorageConfig(output_prefix="executions"),
        staging_root=tmp_path,
    )

    with pytest.raises(KubernetesArtifactCollectionError, match="failed to download"):
        await collector.collect("model-jobs/job-open", _config())

    output_dir = tmp_path / "model-jobs" / "job-open" / "output" / "reports"
    assert not (output_dir / "result.json").exists()
    assert not (output_dir / "result.json.part").exists()
