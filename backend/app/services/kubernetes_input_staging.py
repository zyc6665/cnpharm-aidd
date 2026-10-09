"""Stage task input files into the object store used by Kubernetes Jobs."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.execution.contracts import ExecutionInput
from app.models.artifacts import ArtifactVersion
from app.models.files import File as FileModel
from app.files.storage_path import safe_storage_filename


class KubernetesInputStagingError(ValueError):
    """Raised when a task input cannot be safely staged for a Kubernetes Job."""


async def stage_kubernetes_inputs(
    db: Any,
    *,
    task: Any,
    attempt_id: str,
    storage: Any,
    prefix: str = "inputs",
) -> list[ExecutionInput]:
    """Upload verified task files and return immutable object-store descriptors."""
    task_inputs = getattr(task, "inputs", None)
    file_ids = list(getattr(task_inputs, "file_ids", None) or [])
    extra_data = getattr(task, "extra_data", None)
    extra_data = extra_data if isinstance(extra_data, Mapping) else {}
    slot_by_file_id = _reverse_mapping(extra_data.get("standard_input_uploads"))
    version_by_slot = extra_data.get("input_bindings")
    version_by_slot = dict(version_by_slot) if isinstance(version_by_slot, Mapping) else {}
    materialized_bindings = extra_data.get("materialized_standard_input_bindings")
    if isinstance(materialized_bindings, Mapping):
        version_by_slot.update(materialized_bindings)

    binding_by_file_id, bound_file_ids = await _load_standard_input_bindings(
        db,
        version_by_slot=version_by_slot,
    )
    for file_id, binding in binding_by_file_id.items():
        slot_by_file_id.setdefault(file_id, binding["slot"])
    file_ids.extend(bound_file_ids)
    file_ids = list(dict.fromkeys(str(file_id) for file_id in file_ids))
    if not file_ids:
        return []

    normalized_prefix = _safe_key(prefix)
    result = await db.execute(select(FileModel).where(FileModel.id.in_(file_ids)))
    records = {str(record.id): record for record in result.scalars().all()}
    missing = [file_id for file_id in file_ids if file_id not in records]
    if missing:
        raise KubernetesInputStagingError(
            "Kubernetes task inputs were not found: " + ", ".join(missing)
        )

    inputs: list[ExecutionInput] = []
    seen_file_ids: set[str] = set()
    for index, file_id in enumerate(file_ids):
        normalized_file_id = str(file_id)
        if normalized_file_id in seen_file_ids:
            continue
        seen_file_ids.add(normalized_file_id)
        record = records[normalized_file_id]
        content = await _download(
            storage,
            str(record.storage_path),
            storage_backend=getattr(record, "storage_backend", None),
        )
        actual_sha = hashlib.sha256(content).hexdigest()
        expected_sha = str(record.sha256 or "").lower()
        if actual_sha != expected_sha:
            raise KubernetesInputStagingError(
                f"Kubernetes input checksum mismatch for file {normalized_file_id}"
            )

        slot_name = slot_by_file_id.get(normalized_file_id)
        input_name = _safe_segment(slot_name or f"file-{index}")
        filename = safe_storage_filename(str(record.filename or "file"))
        binding = binding_by_file_id.get(normalized_file_id, {})
        object_key = "/".join(
            (
                normalized_prefix,
                _safe_segment(str(task.id)),
                _safe_segment(attempt_id),
                input_name,
                _safe_segment(filename),
            )
        )
        await storage.upload(content, object_key, getattr(record, "content_type", None))
        inputs.append(
            ExecutionInput(
                artifact_version_id=str(version_by_slot.get(slot_name) or normalized_file_id),
                name=input_name,
                uri=object_key,
                sha256=actual_sha,
                role=binding.get("role"),
                artifact_type=binding.get("artifact_type"),
                content_type=getattr(record, "content_type", None),
                metadata=binding.get("metadata"),
            )
        )
    return inputs


async def _load_standard_input_bindings(
    db: Any,
    *,
    version_by_slot: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    version_to_slot = {
        str(version_id): str(slot)
        for slot, version_id in version_by_slot.items()
        if slot and version_id
    }
    if not version_to_slot:
        return {}, []

    result = await db.execute(
        select(ArtifactVersion)
        .options(
            selectinload(ArtifactVersion.artifact),
            selectinload(ArtifactVersion.files),
        )
        .where(ArtifactVersion.id.in_(list(version_to_slot)))
    )
    bindings: dict[str, dict[str, Any]] = {}
    file_ids: list[str] = []
    for version in result.scalars().all():
        version_id = str(version.id)
        slot = version_to_slot.get(version_id)
        if slot is None:
            continue
        manifest = version.manifest_json if isinstance(version.manifest_json, Mapping) else {}
        artifact = getattr(version, "artifact", None)
        artifact_type = _artifact_type(artifact, manifest)
        metadata = manifest.get("metadata")
        metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
        for link in getattr(version, "files", []) or []:
            file_id = str(getattr(link, "file_id", ""))
            role = str(getattr(link, "role", "") or "")
            if not file_id or not role or not artifact_type:
                continue
            file_ids.append(file_id)
            bindings[file_id] = {
                "slot": slot,
                "role": role,
                "artifact_type": artifact_type,
                "metadata": metadata,
            }
    return bindings, file_ids


def _artifact_type(artifact: Any, manifest: Mapping[str, Any]) -> str | None:
    standard_type = getattr(artifact, "standard_type", None)
    standard_version = getattr(artifact, "standard_version", None)
    if standard_type and standard_version:
        return f"{standard_type}@{standard_version}"
    manifest_type = manifest.get("type")
    return str(manifest_type) if manifest_type else None


async def _download(
    storage: Any,
    path: str,
    *,
    storage_backend: str | None = None,
) -> bytes:
    if storage_backend == "local":
        try:
            return Path(path).read_bytes()
        except OSError as exc:
            raise KubernetesInputStagingError(
                f"failed to read local Kubernetes input: {path}"
            ) from exc
    try:
        content = await storage.download(path)
    except Exception as exc:
        raise KubernetesInputStagingError(f"failed to read Kubernetes input: {path}") from exc
    if not isinstance(content, bytes):
        raise KubernetesInputStagingError(f"storage returned non-bytes input: {path}")
    return content


def _reverse_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(file_id): str(slot_name)
        for slot_name, file_id in value.items()
        if slot_name and file_id
    }


def _safe_key(value: str) -> str:
    parts = str(value).strip("/").split("/")
    if not parts or any(not part for part in parts):
        raise KubernetesInputStagingError("Kubernetes input prefix is empty")
    return "/".join(_safe_segment(part) for part in parts)


def _safe_segment(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value) or value in {".", ".."}:
        raise KubernetesInputStagingError(f"unsafe Kubernetes input path segment: {value}")
    return value
