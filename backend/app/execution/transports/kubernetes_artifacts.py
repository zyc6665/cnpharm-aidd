"""Object-storage result collection for managed Kubernetes Jobs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig
from app.execution.contracts import ExecutionArtifactCollection, ProducedArtifact
from app.execution.standard_contracts import StandardExecutionResult, safe_output_relative_path


class KubernetesTransportError(RuntimeError):
    """Raised when the Kubernetes execution boundary cannot complete an operation."""


class KubernetesArtifactCollectionError(KubernetesTransportError):
    """Raised when a Job result cannot be safely collected from object storage."""


class ObjectStorageReader(Protocol):
    async def download(self, path: str) -> bytes: ...


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
                    try:
                        content = await self._storage.download(object_key)
                    except Exception as exc:
                        raise KubernetesArtifactCollectionError(
                            f"failed to download Kubernetes output object: {object_key}"
                        ) from exc
                    actual_sha = hashlib.sha256(content).hexdigest()
                    if actual_sha != str(file_ref.sha256).lower():
                        raise KubernetesArtifactCollectionError(
                            f"Kubernetes output checksum mismatch: {relative_path}"
                        )
                    destination = output_root / relative_path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)
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
