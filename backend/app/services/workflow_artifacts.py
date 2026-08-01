"""Workflow artifact extraction and annotation service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.files import File as FileModel


def file_download_url(file_id: str) -> str:
    return f"/api/v1/files/{file_id}/download"


async def load_task_output_files(
    db: AsyncSession,
    file_ids: list[str],
) -> list[dict[str, Any]]:
    if not file_ids:
        return []

    result = await db.execute(select(FileModel).where(FileModel.id.in_(file_ids)))
    files_by_id = {file.id: file for file in result.scalars().all()}
    output_files: list[dict[str, Any]] = []

    for file_id in file_ids:
        file_record = files_by_id.get(str(file_id))
        if not file_record:
            continue
        output_files.append(
            {
                "id": file_record.id,
                "filename": file_record.filename,
                "original_name": (file_record.file_meta or {}).get("original_name"),
                "content_type": file_record.content_type,
                "url": file_download_url(file_record.id),
                "path": file_record.storage_path,
            }
        )

    return output_files


def required_outputs_present(
    *,
    capability: Any,
    semantic_outputs: dict[str, dict[str, Any]],
) -> bool:
    return all(
        output.semantic_type in semantic_outputs
        for output in capability.outputs
        if output.required and output.source != "artifact"
    )


def describe_missing_required_outputs(
    *,
    capability: Any,
    semantic_outputs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    missing_outputs: list[dict[str, Any]] = []
    for output in capability.outputs:
        if (
            not output.required
            or output.source == "artifact"
            or output.semantic_type in semantic_outputs
        ):
            continue
        missing_outputs.append(
            {
                "semantic_type": output.semantic_type,
                "source": output.source,
                "path": output.path,
                "required": output.required,
                "match": {
                    "extension": output.match.extension if output.match else None,
                    "filename_contains_any": list(output.match.filename_contains_any or ())
                    if output.match
                    else [],
                    "content_type": output.match.content_type if output.match else None,
                },
            }
        )
    return missing_outputs


def format_missing_required_outputs_error(missing_outputs: list[dict[str, Any]]) -> str:
    if not missing_outputs:
        return "Workflow node task succeeded but required semantic outputs are missing"

    details: list[str] = []
    for item in missing_outputs:
        fragments = [str(item.get("semantic_type") or "unknown_output")]
        source = str(item.get("source") or "")
        match = item.get("match") if isinstance(item.get("match"), dict) else {}
        if source:
            fragments.append(f"source={source}")
        if source == "output_data" and item.get("path"):
            fragments.append(f"path={item['path']}")
        if match.get("extension"):
            fragments.append(f"extension={match['extension']}")
        filename_contains_any = match.get("filename_contains_any") or []
        if filename_contains_any:
            fragments.append(
                "filename_contains_any=" + ",".join(str(value) for value in filename_contains_any)
            )
        if match.get("content_type"):
            fragments.append(f"content_type={match['content_type']}")
        details.append("[" + " ".join(fragments) + "]")

    return "Workflow node missing required semantic outputs: " + "; ".join(details)


def extract_standard_artifacts(output_data: Any) -> dict[str, Any]:
    """Extract the standard Artifact summary attached to a task result."""
    if not isinstance(output_data, dict):
        return {}
    standard_artifacts = output_data.get("standard_artifacts")
    if isinstance(standard_artifacts, dict):
        return dict(standard_artifacts)
    nested = output_data.get("result")
    if isinstance(nested, dict) and isinstance(nested.get("standard_artifacts"), dict):
        return dict(nested["standard_artifacts"])
    return {}


def required_standard_artifacts_present(
    *,
    declared_outputs: list[dict[str, Any]],
    standard_artifacts: dict[str, Any],
) -> bool:
    missing_outputs = describe_missing_required_standard_artifacts(
        declared_outputs=declared_outputs,
        standard_artifacts=standard_artifacts,
    )
    return not missing_outputs


def describe_missing_required_standard_artifacts(
    *,
    declared_outputs: list[dict[str, Any]],
    standard_artifacts: dict[str, Any],
) -> list[dict[str, Any]]:
    version_ids = standard_artifacts.get("artifact_version_ids_by_ref")
    if not isinstance(version_ids, dict):
        version_ids = {}
    file_ids = standard_artifacts.get("file_ids_by_artifact_ref")
    if not isinstance(file_ids, dict):
        file_ids = {}

    missing_outputs: list[dict[str, Any]] = []
    for declaration in declared_outputs:
        if not isinstance(declaration, dict) or not declaration.get("required", True):
            continue
        output_name = str(declaration.get("name") or "")
        if not output_name:
            continue
        if _has_artifact_ref(version_ids, output_name) and _has_artifact_ref(file_ids, output_name):
            continue
        missing_outputs.append(
            {
                "name": output_name,
                "semantic_type": str(declaration.get("type") or ""),
                "source": "artifact",
                "path": output_name,
                "required": True,
                "match": {
                    "extension": None,
                    "filename_contains_any": [],
                    "content_type": None,
                },
            }
        )
    return missing_outputs


def format_missing_required_standard_artifacts_error(missing_outputs: list[dict[str, Any]]) -> str:
    if not missing_outputs:
        return "Workflow node task succeeded but required standard artifacts are missing"
    details = [
        f"[{item.get('name') or item.get('path') or 'unknown_output'} "
        f"type={item.get('semantic_type') or 'unknown_type'}]"
        for item in missing_outputs
    ]
    return "Workflow node missing required standard artifacts: " + "; ".join(details)


def standard_artifact_file_ids(summary: dict[str, Any], output_name: str) -> list[str]:
    """Return file IDs for a standard Artifact output name, including cardinality-many refs."""
    file_ids_by_ref = summary.get("file_ids_by_artifact_ref")
    if not isinstance(file_ids_by_ref, dict):
        return []

    refs = [output_name]
    refs.extend(
        sorted(
            ref
            for ref in file_ids_by_ref
            if isinstance(ref, str) and ref.startswith(f"{output_name}[")
        )
    )

    file_ids: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        raw_file_ids = file_ids_by_ref.get(ref)
        if isinstance(raw_file_ids, str):
            candidates = [raw_file_ids]
        elif isinstance(raw_file_ids, list):
            candidates = [str(file_id) for file_id in raw_file_ids if file_id]
        else:
            candidates = []
        for file_id in candidates:
            if file_id not in seen:
                seen.add(file_id)
                file_ids.append(file_id)
    return file_ids


def _has_artifact_ref(values_by_ref: dict[str, Any], output_name: str) -> bool:
    if output_name in values_by_ref and values_by_ref[output_name]:
        return True
    return any(
        bool(value)
        for ref, value in values_by_ref.items()
        if isinstance(ref, str) and ref.startswith(f"{output_name}[")
    )


async def annotate_semantic_output_files(
    db: AsyncSession,
    *,
    semantic_outputs: dict[str, dict[str, Any]],
) -> None:
    semantic_type_by_file_id = {
        str(value["file_id"]): semantic_type
        for semantic_type, value in semantic_outputs.items()
        if value.get("source") == "output_files" and value.get("file_id")
    }
    if not semantic_type_by_file_id:
        return

    result = await db.execute(
        select(FileModel).where(FileModel.id.in_(list(semantic_type_by_file_id.keys())))
    )
    for file_record in result.scalars().all():
        file_meta = dict(file_record.file_meta or {})
        file_meta["semantic_type"] = semantic_type_by_file_id[file_record.id]
        file_meta["semantic_source"] = "workflow_output"
        file_record.file_meta = file_meta
        db.add(file_record)
