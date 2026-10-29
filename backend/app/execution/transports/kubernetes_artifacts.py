"""Object-storage result collection for managed Kubernetes Jobs."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig
from app.execution.contracts import ExecutionArtifactCollection, ProducedArtifact
from app.execution.standard_contracts import StandardExecutionResult, safe_output_relative_path

logger = logging.getLogger(__name__)


class KubernetesTransportError(RuntimeError):
    """Raised when the Kubernetes execution boundary cannot complete an operation."""


class KubernetesArtifactCollectionError(KubernetesTransportError):
    """Raised when a Job result cannot be safely collected from object storage."""


class ObjectStorageReader(Protocol):
    async def download(self, path: str) -> bytes: ...

    def open_stream(
        self, path: str, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]: ...


@dataclass(frozen=True)
class KubernetesObjectStorageConfig:
    """Platform-owned object key layout used by Job runners and collectors."""

    output_prefix: str = "executions"
    result_filename: str = "result.json"


class KubernetesArtifactCollector:
    """Download and verify a result.v2 envelope emitted by a Kubernetes Job."""

    def __init__(
        self,
        storage: ObjectStorageReader,
        *,
        storage_config: KubernetesObjectStorageConfig,
        staging_root: Path,
    ):
        self._storage = storage
        self._storage_config = storage_config
        self._staging_root = Path(staging_root)

    async def collect(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
    ) -> ExecutionArtifactCollection:
        namespace, job_name = _split_external_id(external_id)
        if namespace != config.namespace:
            raise KubernetesArtifactCollectionError(
                "Kubernetes external_id namespace does not match execution config"
            )
        prefix = self._object_prefix(namespace, job_name)
        result_key = f"{prefix}/{self._storage_config.result_filename}"
        try:
            result_bytes = await self._storage.download(result_key)
        except Exception as exc:
            raise KubernetesArtifactCollectionError(
                f"failed to download Kubernetes result manifest: {result_key}"
            ) from exc

        try:
            result_payload = json.loads(result_bytes.decode("utf-8"))
            result = StandardExecutionResult.model_validate(result_payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise KubernetesArtifactCollectionError(
                f"Kubernetes result manifest is not a valid result.v2 envelope: {exc}"
            ) from exc

        source_root = self._staging_root / _safe_segment(namespace) / _safe_segment(job_name)
        output_root = source_root / "output"
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / self._storage_config.result_filename).write_bytes(result_bytes)

        artifacts: list[ProducedArtifact] = []
        for artifact_value in result.artifacts.values():
            values = artifact_value if isinstance(artifact_value, list) else [artifact_value]
            for artifact in values:
                for file_ref in artifact.files.values():
                    relative_path = _safe_result_path(file_ref.path)
                    object_key = f"{prefix}/{relative_path}"
                    destination = output_root / relative_path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    actual_sha = await self._download_verify_and_stage(
                        object_key=object_key,
                        destination=destination,
                        relative_path=relative_path,
                        expected_sha=str(file_ref.sha256).lower(),
                    )
                    artifacts.append(
                        ProducedArtifact(
                            filename=destination.name,
                            path=relative_path,
                            content_type=file_ref.content_type,
                            sha256=actual_sha,
                            artifact_type=artifact.type,
                        )
                    )

        return ExecutionArtifactCollection(
            artifacts=tuple(artifacts),
            result_payload=result.model_dump(mode="json"),
            source_root=output_root,
        )

    async def _download_verify_and_stage(
        self,
        *,
        object_key: str,
        destination: Path,
        relative_path: str,
        expected_sha: str,
    ) -> str:
        """流式下载对象 → 增量算 sha256 → 写入 staging 文件，峰值内存 = 1 个 chunk。

        选择「先落同盘临时文件（``.part``）再原子改名」而不是 ``store_file_path``：
        ``store_file_path`` 需要 ``AsyncSession`` 才能写 ``File`` 记录并把内容复制到平台
        存储，而采集器的契约只是把字节暂存到 ``staging_root`` 并返回 ``source_root`` 供
        下游摄取，引入 DB 会话会造成双份存储并泄漏未提交的文件行。这里直接按块写目标
        文件，校验通过后再 ``os.replace``，既保持 1MB 峰值内存，又保证失败时不留半成品。
        """
        part_path = destination.with_name(destination.name + ".part")
        digest = hashlib.sha256()
        try:
            with part_path.open("wb") as handle:
                async for chunk in self._storage.open_stream(object_key):
                    if not chunk:
                        continue
                    digest.update(chunk)
                    handle.write(chunk)
        except Exception as exc:
            part_path.unlink(missing_ok=True)
            logger.exception(
                "Failed to stream Kubernetes output object: %s", object_key
            )
            raise KubernetesArtifactCollectionError(
                f"failed to download Kubernetes output object: {object_key}"
            ) from exc

        actual_sha = digest.hexdigest()
        if actual_sha != expected_sha:
            part_path.unlink(missing_ok=True)
            raise KubernetesArtifactCollectionError(
                f"Kubernetes output checksum mismatch: {relative_path}"
            )
        try:
            os.replace(part_path, destination)
        except OSError as exc:
            # os.replace 之前的所有失败都已清理；replace 自身失败也不能留下半截文件。
            part_path.unlink(missing_ok=True)
            logger.exception(
                "Failed to finalize Kubernetes output object: %s", object_key
            )
            raise KubernetesArtifactCollectionError(
                f"failed to finalize Kubernetes output object: {object_key}"
            ) from exc
        return actual_sha

    def _object_prefix(self, namespace: str, job_name: str) -> str:
        prefix = _safe_prefix(self._storage_config.output_prefix)
        parts = [*prefix, _safe_segment(namespace), _safe_segment(job_name)]
        return "/".join(parts)


def _split_external_id(external_id: str) -> tuple[str, str]:
    parts = str(external_id).split("/", 1)
    if len(parts) != 2 or not all(parts):
        raise KubernetesArtifactCollectionError(
            "Kubernetes external_id must be formatted as namespace/job"
        )
    return parts[0], parts[1]


def _safe_segment(value: str) -> str:
    if value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise KubernetesArtifactCollectionError(f"Unsafe Kubernetes object key segment: {value}")
    return value


def _safe_prefix(value: str) -> list[str]:
    parts = [part for part in str(value).strip("/").split("/") if part]
    if not parts:
        raise KubernetesArtifactCollectionError("Kubernetes object storage prefix is empty")
    return [_safe_segment(part) for part in parts]


def _safe_result_path(value: Any) -> str:
    try:
        return safe_output_relative_path(str(value))
    except ValueError as exc:
        raise KubernetesArtifactCollectionError(str(exc)) from exc
