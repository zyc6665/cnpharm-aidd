"""Traceability: freeze task inputs and export the 追溯包 (docs/04 §9.2, docs/05 §10.1).

The delivery line has to answer one question for every result, for as long as the
record is kept: *"what exactly produced this?"* (docs/01 §11.2 G-3). Recomputing
that answer from live tables does not work — the file behind a `file:` URN can be
superseded, a pocket can be re-selected, a candidate set can change. So the inputs
are frozen into ``task_input_snapshots`` at submission time and only ever read
afterwards.

Two things live here:

* :func:`record_task_inputs` — called from ``create_and_schedule_tool_task`` in the
  same transaction as the ``tasks`` row, so a task can never exist without its
  input snapshot.
* :func:`build_traceability_package` — assembles the six metadata groups docs/01
  §11.2 requires (输入快照 / 执行环境 / 运行参数 / 执行过程 / 输出产物 / 归属关系)
  into one JSON document.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.files import File as FileModel
from app.models.tasks import Task, TaskInput, TaskLog
from app.models.traceability import TaskInputSnapshot
from app.models.users import User
from app.services.tool_contracts import build_tool_contract

#: Input roles from docs/04 §9.2 (RECEPTOR / LIGAND / SEQUENCE / POCKET / SET)
#: plus ``FILE`` for platform files that fill no declared semantic slot.
INPUT_ROLE_RECEPTOR = "RECEPTOR"
INPUT_ROLE_LIGAND = "LIGAND"
INPUT_ROLE_SEQUENCE = "SEQUENCE"
INPUT_ROLE_POCKET = "POCKET"
INPUT_ROLE_SET = "SET"
INPUT_ROLE_FILE = "FILE"

#: ``semantic_type`` prefix -> input role. Order matters: the first match wins.
_SEMANTIC_ROLE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("protein_structure", INPUT_ROLE_RECEPTOR),
    ("binding_pocket", INPUT_ROLE_POCKET),
    ("ligand_structure", INPUT_ROLE_LIGAND),
    ("molecule_table", INPUT_ROLE_LIGAND),
    ("candidate_set", INPUT_ROLE_SET),
)


def role_for_semantic_type(semantic_type: str | None) -> str | None:
    """Map a standard Artifact semantic type onto a snapshot input role."""
    value = str(semantic_type or "").strip()
    if not value:
        return None
    for prefix, role in _SEMANTIC_ROLE_PREFIXES:
        if value.startswith(prefix):
            return role
    return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def sequence_sha256(sequence: str | None) -> str | None:
    """Hash a raw sequence so the snapshot pins content, not just a protein id."""
    if not sequence:
        return None
    return hashlib.sha256(sequence.encode("utf-8")).hexdigest()


def _slot_semantic_types(contract: Mapping[str, Any]) -> dict[str, str]:
    artifacts = contract.get("artifacts")
    inputs = artifacts.get("inputs") if isinstance(artifacts, dict) else []
    mapping: dict[str, str] = {}
    for slot in inputs or []:
        if not isinstance(slot, dict):
            continue
        name = str(slot.get("name") or "")
        if name:
            mapping[name] = str(slot.get("type") or "")
    return mapping


async def _file_rows(db: AsyncSession, file_ids: Iterable[str]) -> dict[str, FileModel]:
    ids = [str(file_id) for file_id in file_ids if file_id]
    if not ids:
        return {}
    rows = (await db.execute(select(FileModel).where(FileModel.id.in_(ids)))).scalars().all()
    return {str(row.id): row for row in rows}


def _build_snapshot(
    *,
    task_id: str,
    input_role: str,
    ordinal: int,
    entity_type: str | None = None,
    entity_id: str | None = None,
    urn: str | None = None,
    sha256: str | None = None,
    data_version: int | None = None,
    file_id: str | None = None,
    detail: Mapping[str, Any] | None = None,
) -> TaskInputSnapshot:
    return TaskInputSnapshot(
        task_id=task_id,
        input_role=input_role,
        ordinal=ordinal,
        entity_type=entity_type,
        entity_id=entity_id,
        urn=urn,
        sha256=sha256,
        data_version=data_version,
        file_id=file_id,
        detail=dict(detail or {}),
    )


async def record_task_inputs(
    db: AsyncSession,
    *,
    task: Task,
    tool_version: Any,
    prepared: Any,
    extra_data: Mapping[str, Any] | None = None,
) -> list[TaskInputSnapshot]:
    """Freeze the inputs a task consumed. Call inside the task's transaction.

    ``prepared`` is the ``PreparedRun`` from ``prepare_run`` — the only authoritative
    entry point for run inputs (docs/architecture/15), which is why the snapshot is
    derived from it rather than from ``task_inputs`` after the fact.
    """
    from app.services.domain_targets import file_urn  # local import: avoids a cycle

    contract = build_tool_contract(None, tool_version=tool_version) if tool_version else {}
    semantics = _slot_semantic_types(contract)
    task_id = str(task.id)

    bindings: Mapping[str, str] = dict(getattr(prepared, "input_bindings", {}) or {})
    file_ids: list[str] = [str(item) for item in (getattr(prepared, "file_ids", []) or [])]

    # ``standard_input_uploads`` 是「slot 名 -> 用户上传的文件 id」，而
    # ``materialized_standard_input_bindings`` 是平台据此物化出的 ArtifactVersion。
    # 追溯要回答的是「用户给了什么」，所以文件行是主记录、排在前；物化出的
    # ArtifactVersion 只作为派生载体跟在后面，并指回它来自哪个文件。
    uploads: Mapping[str, str] = {
        str(key): str(value)
        for key, value in ((extra_data or {}).get("standard_input_uploads") or {}).items()
    }
    materialized: Mapping[str, str] = {
        str(key): str(value)
        for key, value in (
            (extra_data or {}).get("materialized_standard_input_bindings") or {}
        ).items()
    }
    derived_by_version: dict[str, str] = {}
    for slot_name, version_id in materialized.items():
        file_id = uploads.get(slot_name)
        if file_id:
            derived_by_version[version_id] = file_id

    files = await _file_rows(db, list(uploads.values()) + file_ids)

    rows: list[TaskInputSnapshot] = []
    counters: dict[str, int] = {}

    def next_ordinal(role: str) -> int:
        value = counters.get(role, 0)
        counters[role] = value + 1
        return value

    # 先写用户直接提交的文件（每个 slot 一条）。
    for slot_name, file_id in uploads.items():
        role = role_for_semantic_type(semantics.get(slot_name)) or INPUT_ROLE_FILE
        record = files.get(file_id)
        if record is None:
            # The file vanished between validation and snapshotting; keep a stub so
            # the traceability package still shows that something was requested.
            rows.append(
                _build_snapshot(
                    task_id=task_id,
                    input_role=role,
                    ordinal=next_ordinal(role),
                    entity_type="file",
                    entity_id=file_id,
                    urn=file_urn(file_id),
                    detail={"missing": True, "slots": [slot_name]},
                )
            )
            continue
        rows.append(
            _build_snapshot(
                task_id=task_id,
                input_role=role,
                ordinal=next_ordinal(role),
                entity_type="file",
                entity_id=file_id,
                urn=file_urn(file_id),
                sha256=record.sha256,
                file_id=file_id,
                detail={
                    "filename": record.filename,
                    "content_type": record.content_type,
                    "size_bytes": record.size_bytes,
                    "source_type": record.source_type,
                    "slots": [slot_name],
                },
            )
        )

    # 再写 ArtifactVersion 绑定（含上面物化出来的那些）。
    for slot_name, artifact_version_id in bindings.items():
        version = await db.get(ArtifactVersion, artifact_version_id)
        artifact = await db.get(Artifact, version.artifact_id) if version else None
        role = role_for_semantic_type(
            getattr(artifact, "semantic_type", None) or semantics.get(slot_name)
        ) or INPUT_ROLE_FILE
        detail: dict[str, Any] = {
            "slot": slot_name,
            "semantic_type": getattr(artifact, "semantic_type", None),
            "standard_type": getattr(artifact, "standard_type", None),
            "standard_version": getattr(artifact, "standard_version", None),
            "filename": getattr(version, "filename", None),
        }
        source_file_id = derived_by_version.get(str(artifact_version_id))
        if source_file_id:
            detail["derived_from_file"] = source_file_id
        rows.append(
            _build_snapshot(
                task_id=task_id,
                input_role=role,
                ordinal=next_ordinal(role),
                entity_type="artifact_version",
                entity_id=str(artifact_version_id),
                urn=f"artifact:{artifact_version_id}",
                sha256=getattr(version, "sha256", None),
                data_version=getattr(version, "version", None),
                detail=detail,
            )
        )

    # 最后是其余没有落到任何 slot 的文件（历史 params.input_files 投影出来的）。
    claimed = set(uploads.values())
    for file_id in file_ids:
        if file_id in claimed:
            continue
        record = files.get(file_id)
        if record is None:
            rows.append(
                _build_snapshot(
                    task_id=task_id,
                    input_role=INPUT_ROLE_FILE,
                    ordinal=next_ordinal(INPUT_ROLE_FILE),
                    entity_type="file",
                    entity_id=file_id,
                    urn=file_urn(file_id),
                    detail={"missing": True},
                )
            )
            continue
        rows.append(
            _build_snapshot(
                task_id=task_id,
                input_role=INPUT_ROLE_FILE,
                ordinal=next_ordinal(INPUT_ROLE_FILE),
                entity_type="file",
                entity_id=file_id,
                urn=file_urn(file_id),
                sha256=record.sha256,
                file_id=file_id,
                detail={
                    "filename": record.filename,
                    "content_type": record.content_type,
                    "size_bytes": record.size_bytes,
                    "source_type": record.source_type,
                },
            )
        )

    domain = (extra_data or {}).get("domain")
    if isinstance(domain, Mapping):
        domain_rows = await _domain_snapshots(db, task_id=task_id, domain=domain, counters=counters)
        rows.extend(domain_rows)

    for row in rows:
        db.add(row)
    await db.flush()
    return rows


async def _domain_snapshots(
    db: AsyncSession,
    *,
    task_id: str,
    domain: Mapping[str, Any],
    counters: dict[str, int],
) -> list[TaskInputSnapshot]:
    """Snapshot the domain entity a task was launched from (M2/M3/M5 bizRef)."""
    from app.models.targets import Pocket, Protein, ProteinStructure

    def next_ordinal(role: str) -> int:
        value = counters.get(role, 0)
        counters[role] = value + 1
        return value

    kind = str(domain.get("kind") or "")
    rows: list[TaskInputSnapshot] = []

    protein_id = domain.get("protein_id")
    if protein_id:
        protein = await db.get(Protein, str(protein_id))
        if protein is not None:
            rows.append(
                _build_snapshot(
                    task_id=task_id,
                    input_role=INPUT_ROLE_SEQUENCE,
                    ordinal=next_ordinal(INPUT_ROLE_SEQUENCE),
                    entity_type="protein",
                    entity_id=str(protein.id),
                    sha256=sequence_sha256(protein.sequence),
                    data_version=protein.current_version,
                    detail={
                        "name": protein.name,
                        "seq_length": protein.seq_length,
                        "source": protein.source,
                        "domain_kind": kind,
                    },
                )
            )

    structure_id = domain.get("structure_id")
    if structure_id:
        structure = await db.get(ProteinStructure, str(structure_id))
        if structure is not None:
            rows.append(
                _build_snapshot(
                    task_id=task_id,
                    input_role=INPUT_ROLE_RECEPTOR,
                    ordinal=next_ordinal(INPUT_ROLE_RECEPTOR),
                    entity_type="protein_structure",
                    entity_id=str(structure.id),
                    urn=structure.structure_urn,
                    sha256=structure.sha256,
                    detail={
                        "source_type": structure.source_type,
                        "model_name": structure.model_name,
                        "model_version": structure.model_version,
                        "domain_kind": kind,
                    },
                )
            )

    pocket_id = domain.get("pocket_id")
    if pocket_id:
        pocket = await db.get(Pocket, str(pocket_id))
        if pocket is not None:
            rows.append(
                _build_snapshot(
                    task_id=task_id,
                    input_role=INPUT_ROLE_POCKET,
                    ordinal=next_ordinal(INPUT_ROLE_POCKET),
                    entity_type="pocket",
                    entity_id=str(pocket.id),
                    detail={
                        "structure_id": str(pocket.structure_id),
                        "rank": pocket.rank,
                        "score": str(pocket.score) if pocket.score is not None else None,
                        "center": {
                            "x": str(pocket.center_x),
                            "y": str(pocket.center_y),
                            "z": str(pocket.center_z),
                        },
                        "domain_kind": kind,
                    },
                )
            )

    return rows


async def load_task_snapshots(db: AsyncSession, *, task_id: str) -> list[TaskInputSnapshot]:
    result = await db.execute(
        select(TaskInputSnapshot)
        .where(TaskInputSnapshot.task_id == task_id)
        .order_by(TaskInputSnapshot.input_role, TaskInputSnapshot.ordinal)
    )
    return list(result.scalars().all())


def serialize_snapshot(row: TaskInputSnapshot) -> dict[str, Any]:
    return {
        "inputRole": row.input_role,
        "ordinal": row.ordinal,
        "entityType": row.entity_type,
        "entityId": row.entity_id,
        "urn": row.urn,
        "sha256": row.sha256,
        "dataVersion": row.data_version,
        "fileId": row.file_id,
        "detail": row.detail or {},
        "recordedAt": _iso(row.created_at),
    }


async def build_traceability_package(
    db: AsyncSession,
    *,
    task: Task,
    tool: Any | None = None,
    tool_version: Any | None = None,
    submitter: User | None = None,
) -> dict[str, Any]:
    """Assemble the 追溯包 JSON for one task (docs/05 §10.1, docs/01 §11.2).

    The six sections are exactly the ones docs/01 §11.2 makes mandatory; anything
    that could not be recovered is reported as ``null`` rather than omitted, so an
    incomplete record is visible instead of looking complete.
    """
    task_id = str(task.id)
    extra_data = dict(getattr(task, "extra_data", None) or {})
    config = dict(getattr(tool_version, "config", None) or {})
    contract = build_tool_contract(tool, tool_version=tool_version) if tool is not None else {}

    snapshots = await load_task_snapshots(db, task_id=task_id)

    # Explicit query instead of ``task.inputs``: the relationship is lazy, and a
    # lazy load inside an async session raises ``MissingGreenlet`` when the caller
    # (e.g. a CLI script or a background job) did not eager-load it.
    task_input = (
        await db.execute(select(TaskInput).where(TaskInput.task_id == task_id))
    ).scalar_one_or_none()

    artifact_rows = (
        await db.execute(
            select(Artifact)
            .options()
            .where(Artifact.source_task_id == task_id)
            .order_by(Artifact.created_at)
        )
    ).scalars().all()

    outputs: list[dict[str, Any]] = []
    for artifact in artifact_rows:
        version = (
            await db.get(ArtifactVersion, artifact.latest_version_id)
            if artifact.latest_version_id
            else None
        )
        outputs.append(
            {
                "kind": "artifact",
                "artifactType": artifact.artifact_type,
                "semanticType": artifact.semantic_type,
                "standardType": artifact.standard_type,
                "standardVersion": artifact.standard_version,
                "urn": f"artifact:{artifact.latest_version_id}" if artifact.latest_version_id else None,
                "sha256": getattr(version, "sha256", None),
                "sizeBytes": getattr(version, "size_bytes", None),
                "filename": getattr(version, "filename", None),
            }
        )

    log_count = (
        await db.execute(
            select(TaskLog.id).where(TaskLog.task_id == task_id).limit(1)
        )
    ).first()

    environment = {
        "image": config.get("image") or config.get("image_ref"),
        "executorType": config.get("type"),
        "tool": {
            "id": str(task.tool_id) if task.tool_id else None,
            "name": getattr(tool, "name", None),
            "slug": getattr(tool, "slug", None),
            "version": getattr(tool_version, "version", None),
            "image": config.get("image") or config.get("image_ref"),
        },
        "model": (extra_data.get("domain") or {}).get("model_ref")
        if isinstance(extra_data.get("domain"), Mapping)
        else None,
        "resourceSnapshot": extra_data.get("resource_snapshot"),
        "contractVersion": contract.get("contract_version"),
    }

    return {
        "taskId": task_id,
        "taskName": task.name,
        "taskType": (extra_data.get("domain") or {}).get("kind")
        if isinstance(extra_data.get("domain"), Mapping)
        else None,
        "status": task.status,
        "submittedBy": {
            "userId": str(task.user_id) if task.user_id else None,
            "displayName": getattr(submitter, "display_name", None),
            "email": getattr(submitter, "email", None),
        },
        "projectId": extra_data.get("project_id"),
        "timeline": {
            "created": _iso(task.created_at),
            "started": _iso(task.started_at),
            "finished": _iso(task.finished_at),
            "executionSeconds": task.execution_time_sec,
            "retryCount": task.retry_count,
        },
        "inputs": [serialize_snapshot(row) for row in snapshots],
        "environment": environment,
        "params": {
            "requested": dict(getattr(task_input, "params", None) or {}),
            "inputBindings": extra_data.get("input_bindings") or {},
        },
        "process": {
            "exitMessage": task.error_message,
            "progressMessage": task.progress_message,
            "logAvailable": log_count is not None,
            "logsEndpoint": f"/api/v1/tasks/{task_id}/logs",
        },
        "outputs": outputs,
        "bizRef": {
            "projectId": extra_data.get("project_id"),
            "domain": extra_data.get("domain"),
        },
        "exportedAt": utcnow().isoformat(),
        "packageVersion": "traceability.v1",
    }


def package_sha256(package: Mapping[str, Any]) -> str:
    """Stable content hash of a package, for the export file name and manifest."""
    payload = json.dumps(package, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "INPUT_ROLE_FILE",
    "INPUT_ROLE_LIGAND",
    "INPUT_ROLE_POCKET",
    "INPUT_ROLE_RECEPTOR",
    "INPUT_ROLE_SEQUENCE",
    "INPUT_ROLE_SET",
    "build_traceability_package",
    "load_task_snapshots",
    "package_sha256",
    "record_task_inputs",
    "role_for_semantic_type",
    "sequence_sha256",
    "serialize_snapshot",
]
