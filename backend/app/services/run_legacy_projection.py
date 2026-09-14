"""Project prepared run files into legacy executor parameter shapes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.files import File as FileModel
from app.services.legacy_file_projection import (
    legacy_file_fields,
    select_legacy_file_field,
)


def tool_version_config(tool_version: Any) -> dict[str, Any]:
    config = getattr(tool_version, "config", None)
    return config if isinstance(config, dict) else {}


async def project_file_to_legacy_params(
    db: AsyncSession,
    *,
    tool_version: Any,
    input_slot: dict[str, Any],
    file_id: str,
    params: dict[str, Any],
    used_fields: set[str] | None = None,
) -> None:
    config = tool_version_config(tool_version)
    executor_type = str(config.get("type") or "")
    if executor_type == "builtin":
        builtin_inputs = (
            params.get("builtin_inputs")
            if isinstance(params.get("builtin_inputs"), dict)
            else {}
        )
        params["builtin_inputs"] = {
            **builtin_inputs,
            str(input_slot.get("type") or input_slot.get("name")): file_id,
        }
        return
    if executor_type != "ssh_job":
        return

    file_record = await db.get(FileModel, file_id)
    if not file_record:
        return
    file_field = legacy_file_field_for_slot(
        config,
        input_slot,
        used_fields=used_fields,
    )
    if not file_field:
        return
    input_files = (
        params.get("input_files")
        if isinstance(params.get("input_files"), dict)
        else {}
    )
    params["input_files"] = {
        **input_files,
        file_field: f"input/{Path(str(file_record.filename)).name}",
    }
    if used_fields is not None:
        used_fields.add(file_field)


def existing_input_file_fields(params: dict[str, Any]) -> set[str]:
    input_files = (
        params.get("input_files")
        if isinstance(params.get("input_files"), dict)
        else {}
    )
    return {str(field) for field in input_files}


def legacy_file_field_for_slot(
    config: dict[str, Any],
    input_slot: dict[str, Any],
    *,
    used_fields: set[str] | None = None,
) -> str | None:
    return select_legacy_file_field(
        input_name=str(input_slot.get("name") or ""),
        standard_type=str(input_slot.get("type") or ""),
        file_fields=legacy_file_fields(config),
        used_fields=used_fields,
    )
