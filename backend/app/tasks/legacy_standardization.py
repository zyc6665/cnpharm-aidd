"""Standardize selected legacy executor outputs into result.v2 envelopes."""

from __future__ import annotations

import csv
import io
import json
import logging
import math
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.files.content import read_file_bytes
from app.files.writer import store_file_bytes
from app.models.files import File as FileModel, FileSourceType
from app.tool_packages.config_resolver import tool_package_manifest_data

logger = logging.getLogger(__name__)


async def append_legacy_standard_result(
    db: AsyncSession,
    *,
    task: Any | None = None,
    tool_version_config: dict[str, Any],
    output_result: dict[str, Any],
    output_file_ids: list[str],
) -> dict[str, Any]:
    if not isinstance(output_result, dict) or _has_standard_result(output_result):
        return output_result

    source_task_id = str(getattr(task, "id", "") or _legacy_output_task_id(output_result) or "unknown-task")
    standard_result: dict[str, Any] | None = None
    if _declares_standard_output(tool_version_config, "pocket", "binding_pocket@1"):
        standard_result = await _legacy_lvpocket_result_v2(
            db,
            output_result=output_result,
            output_file_ids=output_file_ids,
        )
    elif _declares_standard_output(tool_version_config, "properties", "molecule_table@1"):
        standard_result = await _legacy_molp_pc_result_v2(
            db,
            output_result=output_result,
            output_file_ids=output_file_ids,
            source_task_id=source_task_id,
            tool_version_config=tool_version_config,
        )
    elif _declares_standard_output(tool_version_config, "affinity", "molecule_table@1"):
        standard_result = await _legacy_msign_result_v2(
            db,
            output_result=output_result,
            output_file_ids=output_file_ids,
            source_task_id=source_task_id,
        )
    if standard_result is None:
        return output_result

    next_result = dict(output_result)
    next_result["standard_result"] = standard_result
    next_result["output_file_ids"] = _merged_output_file_ids(next_result, output_file_ids)
    return next_result


def _has_standard_result(output_result: dict[str, Any]) -> bool:
    if output_result.get("result_version") == "aidd.sciminer/result.v2":
        return True
    nested = output_result.get("result")
    if isinstance(nested, dict) and nested.get("result_version") == "aidd.sciminer/result.v2":
        return True
    standard_result = output_result.get("standard_result")
    return isinstance(standard_result, dict) and standard_result.get("result_version") == "aidd.sciminer/result.v2"


def _declares_standard_output(config: dict[str, Any], name: str, standard_type: str) -> bool:
    return any(
        item.get("name") == name and item.get("type") == standard_type
        for item in _declared_standard_outputs(config)
    )


def _declared_standard_outputs(config: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = tool_package_manifest_data(config)
    if isinstance(manifest, dict):
        artifacts = manifest.get("artifacts")
        outputs = artifacts.get("outputs") if isinstance(artifacts, dict) else None
        if isinstance(outputs, list):
            return [item for item in outputs if isinstance(item, dict)]

    artifacts = config.get("artifacts")
    outputs = artifacts.get("outputs") if isinstance(artifacts, dict) else None
    return [item for item in outputs or [] if isinstance(item, dict)]

async def _legacy_lvpocket_result_v2(
    db: AsyncSession,
    *,
    output_result: dict[str, Any],
    output_file_ids: list[str],
) -> dict[str, Any] | None:
    legacy = output_result.get("result")
    if not isinstance(legacy, dict):
        return None
    outputs = legacy.get("outputs")
    if not isinstance(outputs, dict):
        return None

    residue = outputs.get("protein_pocket_residues")
    pockets = outputs.get("pockets")
    if not isinstance(residue, dict) or not isinstance(pockets, list) or not pockets:
        return None
    first_pocket = pockets[0]
    if not isinstance(first_pocket, dict):
        return None

    residue_path = str(residue.get("path") or "")
    atom_path = str(first_pocket.get("pdb") or "")
    metadata_path = _prediction_json_path(legacy)
    if not residue_path or not atom_path or not metadata_path:
        return None

    file_records = await _file_records_by_relative_path(db, output_file_ids)
    try:
        residue_ref = _standard_file_ref(file_records, residue_path)
        atom_ref = _standard_file_ref(file_records, atom_path)
        metadata_ref = _standard_file_ref(file_records, metadata_path)
    except KeyError:
        return None

    center = _valid_coordinate_vector(outputs.get("center"))
    bbox = _valid_bbox(outputs.get("bbox"))
    if center is None or bbox is None:
        atom_record = _lookup_file_record(file_records, atom_path)
        geometry = None
        if atom_record is not None and atom_record.storage_path:
            try:
                geometry = _pdb_geometry(await read_file_bytes(atom_record))
            except FileNotFoundError:
                geometry = None
        if geometry is None:
            logger.warning(
                "无法为旧版 LVpocket 输出生成有效 binding_pocket 元数据："
                "center/bbox 缺失或无效，且口袋 PDB 无可解析坐标（%s）",
                atom_ref.get("path"),
            )
            return None
        calculated_center, calculated_bbox = geometry
        center = center or calculated_center
        bbox = bbox or calculated_bbox

    pocket_id = str(first_pocket.get("id") or "pocket0")
    return {
        "result_version": "aidd.sciminer/result.v2",
        "artifacts": {
            "pocket": {
                "type": "binding_pocket@1",
                "name": pocket_id,
                "files": {
                    "residue_pocket_pdb": residue_ref,
                    "atom_pocket_pdb": atom_ref,
                    "pocket_metadata_json": metadata_ref,
                },
                "metadata": {
                    "center": center,
                    "bbox": bbox,
                    "residue_ids": outputs.get("residue_ids") or [],
                    "atom_ids": outputs.get("atom_ids") or [],
                    "source_protein_ref": "input/protein_pdb",
                    "residue_count": residue.get("residue_count"),
                    "atom_count": residue.get("atom_count"),
                    "pocket_count": outputs.get("pocket_count"),
                },
                "summary": {
                    "pocket_id": pocket_id,
                    "pocket_count": outputs.get("pocket_count"),
                    "selected_model": outputs.get("selected_model"),
                    "model_choice": outputs.get("model_choice"),
                },
            }
        },
        "summary": {"standardized_from": "legacy_lvpocket"},
    }


def _valid_coordinate_vector(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    if any(isinstance(component, bool) for component in value):
        return None
    try:
        coordinates = [float(component) for component in value]
    except (TypeError, ValueError):
        return None
    return coordinates if all(math.isfinite(component) for component in coordinates) else None


def _valid_bbox(value: Any) -> dict[str, list[float]] | None:
    if not isinstance(value, dict):
        return None
    minimum = _valid_coordinate_vector(value.get("min"))
    maximum = _valid_coordinate_vector(value.get("max"))
    if minimum is None or maximum is None:
        return None
    if any(low > high for low, high in zip(minimum, maximum)):
        return None
    return {"min": minimum, "max": maximum}


def _pdb_geometry(content: bytes) -> tuple[list[float], dict[str, list[float]]] | None:
    coordinates: list[list[float]] = []
    for line in content.decode("ascii", errors="ignore").splitlines():
        if line[0:6].strip() not in {"ATOM", "HETATM"}:
            continue
        try:
            coordinates.append(
                [float(line[start:end]) for start, end in ((30, 38), (38, 46), (46, 54))]
            )
        except ValueError:
            continue
    if not coordinates:
        return None

    minimum = [min(point[axis] for point in coordinates) for axis in range(3)]
    maximum = [max(point[axis] for point in coordinates) for axis in range(3)]
    center = [
        sum(point[axis] for point in coordinates) / len(coordinates)
        for axis in range(3)
    ]
    if not all(math.isfinite(value) for value in (*minimum, *maximum, *center)):
        return None
    return center, {"min": minimum, "max": maximum}


async def _legacy_molp_pc_result_v2(
    db: AsyncSession,
    *,
    output_result: dict[str, Any],
    output_file_ids: list[str],
    source_task_id: str,
    tool_version_config: dict[str, Any],
) -> dict[str, Any] | None:
    legacy = output_result.get("result")
    if not isinstance(legacy, dict):
        return None
    outputs = legacy.get("outputs")
    if not isinstance(outputs, dict):
        return None
    prediction_path = str(outputs.get("prediction_file") or "")
    if not prediction_path:
        prediction_path = _first_artifact_path(legacy, suffix=".csv") or ""
    if not prediction_path:
        return None

    file_records = await _file_records_by_relative_path(db, output_file_ids)
    table_record = _lookup_file_record(file_records, prediction_path)
    if table_record is None:
        return None
    table_ref = _standard_file_ref(file_records, prediction_path)

    scientific_metadata = _legacy_molp_pc_scientific_metadata(tool_version_config)
    metadata = _molecule_table_metadata(
        table_record,
        source_task_id=source_task_id,
        default_id_field="SMILES",
        model_name="MolP-PC",
    )
    metadata.update(scientific_metadata)
    metadata_ref = await _persist_generated_output_file(
        db,
        output_file_ids=output_file_ids,
        seed_records=file_records,
        relative_path="artifacts/properties/metadata.json",
        content=json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
        content_type="application/json",
    )
    if metadata_ref is None:
        return None

    report = _legacy_molp_pc_report(
        source_task_id=source_task_id,
        metadata=metadata,
        scientific_metadata=scientific_metadata,
    )
    report_ref = await _persist_generated_output_file(
        db,
        output_file_ids=output_file_ids,
        seed_records=file_records,
        relative_path="reports/report.json",
        content=json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
        content_type="application/json",
    )
    if report_ref is None:
        return None

    return {
        "result_version": "aidd.sciminer/result.v2",
        "artifacts": {
            "properties": {
                "type": "molecule_table@1",
                "name": f"{source_task_id}_molp_pc_admet_predictions",
                "files": {
                    "table_file": table_ref,
                    "metadata_json": metadata_ref,
                },
                "metadata": metadata,
            },
            "report": {
                "type": "run_report@1",
                "name": f"{source_task_id}_molp_pc_adapter_report",
                "files": {"report_json": report_ref},
                "metadata": {
                    "source_task_id": source_task_id,
                    "model_card_ref": scientific_metadata["model_card_ref"],
                    "verification_record_ref": scientific_metadata["verification_record_ref"],
                    "evidence_level": scientific_metadata["evidence_level"],
                },
            }
        },
        "relations": [{"from": "report", "to": "properties", "type": "describes"}],
        "summary": {"standardized_from": "legacy_molp_pc"},
    }


_MOLP_PC_TASK_GROUPS = [
    "Absorption",
    "Distribution",
    "Excretion",
    "Metabolism",
    "Toxicology",
    "Tox21",
    "Ecotoxicity",
    "LD50",
]


def _legacy_molp_pc_scientific_metadata(tool_version_config: dict[str, Any]) -> dict[str, str]:
    manifest = tool_package_manifest_data(tool_version_config) or {}
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    version = str(metadata.get("version") or "0.1.1")
    return {
        "model_version": version,
        "runtime_ref": _legacy_molp_pc_runtime_ref(manifest),
        "weights_ref": _legacy_molp_pc_weights_ref(manifest),
        "endpoint_ref": f"local_runtime:molp-pc-property-prediction@{version}",
        "evidence_level": "engineering_smoke_only",
        "applicability_domain_status": "unknown",
        "unit_or_label_policy": "per_endpoint_definition_or_unknown",
        "model_card_ref": "example/MolP-PC/tool-package-v2/docs/model-card.md",
        "verification_record_ref": "example/MolP-PC/tool-package-v2/docs/verification-record.md",
    }


def _legacy_molp_pc_runtime_ref(manifest: dict[str, Any]) -> str:
    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    artifacts = runtime.get("artifacts") if isinstance(runtime.get("artifacts"), dict) else {}
    primary = artifacts.get("primary") if isinstance(artifacts.get("primary"), dict) else {}
    image = str(primary.get("image") or "").strip()
    image_digest = str(primary.get("image_digest") or "").strip()
    if image and image_digest:
        return f"container:{image}@{image_digest}"

    fallback = artifacts.get("fallback") if isinstance(artifacts.get("fallback"), dict) else {}
    fallback_uri = str(fallback.get("uri") or "").strip()
    fallback_sha256 = str(fallback.get("sha256") or "").strip()
    if fallback_uri and fallback_sha256:
        return f"conda_pack:{fallback_uri}#sha256:{fallback_sha256}"
    return "local_runtime:legacy_molp_pc"


def _legacy_molp_pc_weights_ref(manifest: dict[str, Any]) -> str:
    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    weights = runtime.get("weights") if isinstance(runtime.get("weights"), dict) else {}
    manifest_uri = str(weights.get("manifest_uri") or "").strip()
    manifest_sha256 = str(weights.get("manifest_sha256") or "").strip()
    if manifest_uri and manifest_sha256:
        return f"{manifest_uri}#sha256:{manifest_sha256}"
    return "unknown"


def _legacy_molp_pc_report(
    *,
    source_task_id: str,
    metadata: dict[str, Any],
    scientific_metadata: dict[str, str],
) -> dict[str, Any]:
    return {
        "tool": "molp-pc-property-prediction",
        "adapter": "legacy_standardization",
        "status": "succeeded",
        "source_task_id": source_task_id,
        "predicted_rows": metadata.get("row_count", 0),
        "property_column_count": metadata.get("property_column_count", 0),
        "property_columns": metadata.get("property_columns", []),
        "task_groups": _MOLP_PC_TASK_GROUPS,
        "scientific_interpretation": {
            "prediction_kind": "basic_admet_prediction",
            "model_name": "MolP-PC",
            **scientific_metadata,
        },
    }


async def _legacy_msign_result_v2(
    db: AsyncSession,
    *,
    output_result: dict[str, Any],
    output_file_ids: list[str],
    source_task_id: str,
) -> dict[str, Any] | None:
    legacy = output_result.get("result")
    if not isinstance(legacy, dict):
        return None
    outputs = legacy.get("outputs")
    if not isinstance(outputs, dict):
        return None
    prediction = outputs.get("prediction")
    if not isinstance(prediction, dict):
        return None

    file_records = await _file_records_by_relative_path(db, output_file_ids)
    row = _legacy_msign_affinity_row(outputs, prediction)
    table_content = _affinity_csv_content(row)
    table_ref = await _persist_generated_output_file(
        db,
        output_file_ids=output_file_ids,
        seed_records=file_records,
        relative_path="artifacts/affinity/msign_affinity.csv",
        content=table_content,
        content_type="text/csv",
    )
    if table_ref is None:
        return None

    metadata = {
        "molecule_id_field": "complex_id",
        "source_task_id": source_task_id,
        "source_input_refs": ["input:protein", "input:ligand"],
        "row_count": 1,
        "property_columns": [column for column in _AFFINITY_COLUMNS if column != "complex_id"],
        "model_name": row.get("model_name") or "MSIGN",
    }
    metadata_ref = await _persist_generated_output_file(
        db,
        output_file_ids=output_file_ids,
        seed_records=file_records,
        relative_path="artifacts/affinity/metadata.json",
        content=json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
        content_type="application/json",
    )
    if metadata_ref is None:
        return None

    return {
        "result_version": "aidd.sciminer/result.v2",
        "artifacts": {
            "affinity": {
                "type": "molecule_table@1",
                "name": f"{source_task_id}_msign_affinity",
                "files": {
                    "table_file": table_ref,
                    "metadata_json": metadata_ref,
                },
                "metadata": metadata,
            }
        },
        "summary": {"standardized_from": "legacy_msign"},
    }


def _prediction_json_path(legacy: dict[str, Any]) -> str | None:
    artifacts = legacy.get("artifacts")
    if not isinstance(artifacts, list):
        return None
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        name = str(item.get("name") or "")
        if path.endswith("prediction.json") or name == "prediction.json":
            return path
    return None


def _first_artifact_path(legacy: dict[str, Any], *, suffix: str) -> str | None:
    artifacts = legacy.get("artifacts")
    if not isinstance(artifacts, list):
        return None
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        name = str(item.get("name") or "")
        if path.endswith(suffix) or name.endswith(suffix):
            return path
    return None


def _legacy_output_task_id(output_result: dict[str, Any]) -> str | None:
    legacy = output_result.get("result")
    outputs = legacy.get("outputs") if isinstance(legacy, dict) else None
    if isinstance(outputs, dict) and outputs.get("task_id"):
        return str(outputs["task_id"])
    return None


def _merged_output_file_ids(
    output_result: dict[str, Any],
    generated_file_ids: list[str],
) -> list[str]:
    merged: list[str] = []
    existing = output_result.get("output_file_ids")
    for file_id in existing if isinstance(existing, list) else []:
        if isinstance(file_id, str) and file_id not in merged:
            merged.append(file_id)
    for file_id in generated_file_ids:
        if file_id not in merged:
            merged.append(file_id)
    return merged


async def _file_records_by_relative_path(
    db: AsyncSession,
    output_file_ids: list[str],
) -> dict[str, FileModel]:
    if not output_file_ids:
        return {}
    records = (
        await db.execute(select(FileModel).where(FileModel.id.in_(output_file_ids)))
    ).scalars().all()
    indexed: dict[str, FileModel] = {}
    for record in records:
        meta = record.file_meta if isinstance(record.file_meta, dict) else {}
        relative_path = meta.get("relative_path")
        if isinstance(relative_path, str) and relative_path:
            indexed[relative_path] = record
        indexed[str(record.filename)] = record
    return indexed


def _lookup_file_record(file_records: dict[str, FileModel], relative_path: str) -> FileModel | None:
    return file_records.get(relative_path) or file_records.get(relative_path.replace("/", "__"))


async def _persist_generated_output_file(
    db: AsyncSession,
    *,
    output_file_ids: list[str],
    seed_records: dict[str, FileModel],
    relative_path: str,
    content: bytes,
    content_type: str,
) -> dict[str, Any] | None:
    seed_record = next(iter(seed_records.values()), None)
    if seed_record is None:
        return None

    filename = relative_path.replace("/", "__")
    record = await store_file_bytes(
        db,
        content=content,
        filename=filename,
        content_type=content_type,
        source_type=FileSourceType.TOOL_OUTPUT,
        project_id=seed_record.project_id,
        owner_id=seed_record.owner_id,
        file_meta={
            "relative_path": relative_path,
            "generated_by": "legacy_standardization",
        },
    )

    if str(record.id) not in output_file_ids:
        output_file_ids.append(str(record.id))
    seed_records[relative_path] = record
    seed_records[filename] = record
    return _standard_file_ref(seed_records, relative_path)


def _molecule_table_metadata(
    table_record: FileModel,
    *,
    source_task_id: str,
    default_id_field: str,
    model_name: str,
) -> dict[str, Any]:
    path = getattr(table_record, "storage_path", None)
    fieldnames: list[str] = []
    row_count = 0
    if path:
        content = Path(str(path)).read_text(encoding="utf-8", errors="replace")
        reader = csv.DictReader(content.splitlines())
        fieldnames = list(reader.fieldnames or [])
        row_count = sum(1 for _row in reader)
    molecule_id_field = default_id_field if default_id_field in fieldnames else (fieldnames[0] if fieldnames else default_id_field)
    property_columns = [field for field in fieldnames if field != molecule_id_field]
    return {
        "molecule_id_field": molecule_id_field,
        "source_task_id": source_task_id,
        "source_input_ref": "input:molecules",
        "row_count": row_count,
        "property_column_count": len(property_columns),
        "property_columns": property_columns,
        "model_name": model_name,
    }


_AFFINITY_COLUMNS = [
    "complex_id",
    "predicted_affinity",
    "predicted_ligand_to_pocket",
    "predicted_pocket_to_ligand",
    "scale",
    "model_name",
    "distance_angstrom",
    "device",
]


def _legacy_msign_affinity_row(outputs: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
    return {
        "complex_id": str(outputs.get("complex_id") or "unknown-complex"),
        "predicted_affinity": prediction.get("predicted_affinity"),
        "predicted_ligand_to_pocket": prediction.get("predicted_ligand_to_pocket"),
        "predicted_pocket_to_ligand": prediction.get("predicted_pocket_to_ligand"),
        "scale": prediction.get("scale", ""),
        "model_name": outputs.get("model_name") or "",
        "distance_angstrom": outputs.get("distance_angstrom") or "",
        "device": outputs.get("device") or "",
    }


def _affinity_csv_content(row: dict[str, Any]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_AFFINITY_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerow({column: row.get(column, "") for column in _AFFINITY_COLUMNS})
    return output.getvalue().encode("utf-8")


def _standard_file_ref(file_records: dict[str, FileModel], relative_path: str) -> dict[str, Any]:
    record = file_records.get(relative_path) or file_records.get(relative_path.replace("/", "__"))
    if record is None:
        raise KeyError(relative_path)
    return {
        "path": relative_path,
        "sha256": str(record.sha256).lower(),
        "content_type": record.content_type,
    }
