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

    async def download(self, path: str) -> bytes:
        if path not in self.objects:
            raise FileNotFoundError(path)
        return self.objects[path]


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
            "result_version": "aidd.sciminer/result.v2",
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

    assert collection.result_payload["result_version"] == "aidd.sciminer/result.v2"
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
            "result_version": "aidd.sciminer/result.v2",
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
