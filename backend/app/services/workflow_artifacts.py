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
        if output.required
    )


def describe_missing_required_outputs(
    *,
    capability: Any,
    semantic_outputs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    missing_outputs: list[dict[str, Any]] = []
    for output in capability.outputs:
        if not output.required or output.semantic_type in semantic_outputs:
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
