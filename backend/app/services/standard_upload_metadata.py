"""Infer metadata for direct standard Artifact uploads."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from app.common.exceptions import ValidationException
from app.files.content import read_file_bytes
from app.models.files import File as FileModel


async def build_standard_upload_metadata(
    *,
    slot_name: str,
    standard_ref: str,
    uploaded_file: FileModel,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source": "direct_upload",
        "input_name": slot_name,
        "standard_type": standard_ref,
        "source_filename": uploaded_file.filename,
        "source_file_id": str(uploaded_file.id),
        "sha256": uploaded_file.sha256,
    }
    if standard_ref == "molecule_table@1":
        metadata.update(
            await _molecule_table_upload_metadata(
                slot_name=slot_name,
                uploaded_file=uploaded_file,
            )
        )
    elif standard_ref == "protein_structure@1":
        metadata.update(await _protein_structure_upload_metadata(slot_name, uploaded_file))
    elif standard_ref == "ligand_structure@1":
        metadata.update(await _ligand_structure_upload_metadata(slot_name, uploaded_file))
    return metadata


async def _molecule_table_upload_metadata(
    *,
    slot_name: str,
    uploaded_file: FileModel,
) -> dict[str, object]:
    columns, row_count = await _read_molecule_table_shape(slot_name, uploaded_file)
    if not columns or row_count < 1:
        raise _invalid_content_error(
            slot_name,
            uploaded_file,
            "molecule_table@1 需要至少一个表头列和一行数据",
        )
    return {
        "source_task_id": str(uploaded_file.id),
        "source_input_ref": f"input:{slot_name}",
        "molecule_id_field": _molecule_id_field(columns),
        "row_count": row_count,
        "column_count": len(columns),
        "columns": columns,
    }


async def _read_molecule_table_shape(slot_name: str, uploaded_file: FileModel) -> tuple[list[str], int]:
    text = await _read_text(uploaded_file)
    if not text:
        return [], 0
    if Path(uploaded_file.filename).suffix.lower() == ".json":
        return _read_json_table_shape(slot_name, uploaded_file, text)
    return _read_csv_shape(text)


def _read_csv_shape(text: str) -> tuple[list[str], int]:
    reader = csv.DictReader(text.splitlines())
    columns = list(reader.fieldnames or [])
    return columns, sum(1 for _row in reader)


def _read_json_table_shape(
    slot_name: str,
    uploaded_file: FileModel,
    text: str,
) -> tuple[list[str], int]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _invalid_content_error(slot_name, uploaded_file, "JSON 文件无法解析") from exc

    rows = _json_table_rows(payload)
    if rows is None:
        return _json_object_shape(payload)
    return _json_rows_shape(rows)


def _json_table_rows(payload: object) -> list[object] | None:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("rows", "data", "items", "molecules"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return None


def _json_rows_shape(rows: list[object]) -> tuple[list[str], int]:
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row:
            column = str(key)
            if column not in seen:
                columns.append(column)
                seen.add(column)
    return columns, len(rows)


def _json_object_shape(payload: object) -> tuple[list[str], int]:
    if not isinstance(payload, dict):
        return [], 0
    return [str(key) for key in payload], 1


def _molecule_id_field(columns: list[str]) -> str:
    lowered = {column.lower(): column for column in columns}
    for candidate in ("molecule_id", "id", "compound_id"):
        if candidate in lowered:
            return lowered[candidate]
    return columns[0] if columns else "molecule_id"


async def _protein_structure_upload_metadata(
    slot_name: str,
    uploaded_file: FileModel,
) -> dict[str, object]:
    stats = await _read_pdb_stats(uploaded_file)
    if stats["atom_count"] < 1:
        raise _invalid_content_error(
            slot_name,
            uploaded_file,
            "protein_structure@1 需要包含 ATOM 或 HETATM 记录",
        )
    return {
        **stats,
        "structure_format": _structure_format(uploaded_file.filename),
        "source_database": "manual",
        "preparation_status": "raw",
    }


async def _ligand_structure_upload_metadata(
    slot_name: str,
    uploaded_file: FileModel,
) -> dict[str, object]:
    await _validate_sdf_content(slot_name, uploaded_file)
    return {
        "ligand_id": Path(uploaded_file.filename).stem or str(uploaded_file.id),
        "source_database": "manual",
    }


async def _read_pdb_stats(uploaded_file: FileModel) -> dict[str, object]:
    text = await _read_text(uploaded_file)
    chains: set[str] = set()
    residues: set[tuple[str, str]] = set()
    atom_count = 0
    for line in text.splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        atom_count += 1
        chain_id = line[21:22].strip() or "_"
        residue_id = line[22:27].strip()
        chains.add(chain_id)
        residues.add((chain_id, residue_id))
    return {
        "chain_ids": sorted(chains),
        "residue_count": len(residues),
        "atom_count": atom_count,
    }


async def _validate_sdf_content(slot_name: str, uploaded_file: FileModel) -> None:
    text = await _read_text(uploaded_file)
    if "$$$$" not in text:
        raise _invalid_content_error(
            slot_name,
            uploaded_file,
            "ligand_structure@1 需要包含 SDF 记录分隔符 $$$$",
        )


def _structure_format(filename: str) -> str:
    extension = Path(filename).suffix.lower().lstrip(".")
    return "cif" if extension == "cif" else "pdb"


async def _read_text(uploaded_file: FileModel) -> str:
    if not uploaded_file.storage_path:
        return ""
    try:
        content = await read_file_bytes(uploaded_file)
    except FileNotFoundError:
        return ""
    return content.decode("utf-8", errors="replace")


def _invalid_content_error(
    slot_name: str,
    uploaded_file: FileModel,
    reason: str,
) -> ValidationException:
    return ValidationException(
        "标准 Artifact 上传内容无效",
        detail={
            "input_name": slot_name,
            "filename": uploaded_file.filename,
            "reason": reason,
        },
    )
