"""分子生成任务的统一评分后处理。"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
import mimetypes
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.files import File as FileModel, FileSourceType
from app.models.tasks import Task, TaskInput
from app.models.tools import Tool, ToolVersion
from app.files.storage_path import get_file_path

logger = logging.getLogger(__name__)

TOP_MOLECULE_LIMIT = 10
SCORE_CSV_NAME = "molecule_scores.csv"
TOP_SDF_NAME = "top10_molecules.sdf"


@dataclass(frozen=True)
class MoleculeCandidate:
    """一个待评分的小分子 SDF 记录。"""

    source_file_id: str
    source_filename: str
    sdf_file: str
    record_index: int
    global_index: int
    sdf_record: str


@dataclass(frozen=True)
class DescriptorScores:
    """QED/SA 等分子性质评分。"""

    smiles: str | None = None
    qed: float | None = None
    sa: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class MoleculeScore:
    candidate: MoleculeCandidate
    smiles: str | None
    qed: float | None
    sa: float | None
    vina_score: float | None
    composite_score: float
    error: str | None = None


def split_sdf_records(text: str) -> list[str]:
    """按 $$$$ 分割 SDF，并保留每条记录的终止符。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    records: list[str] = []

    for part in normalized.split("$$$$"):
        if part.startswith("\n"):
            part = part[1:]
        if not part.strip():
            continue
        record = part.rstrip() + "\n$$$$\n"
        records.append(record)

    return records or ([normalized if normalized.endswith("\n") else f"{normalized}\n"] if normalized.strip() else [])


def _relative_name(file_record: FileModel) -> str:
    meta = file_record.file_meta if isinstance(file_record.file_meta, dict) else {}
    relative_path = meta.get("relative_path")
    return str(relative_path or file_record.filename)


def _is_sdf_file(file_record: FileModel) -> bool:
    name = _relative_name(file_record).lower()
    content_type = (file_record.content_type or "").lower()
    return name.endswith(".sdf") or "mdl-sdfile" in content_type


def _is_sdf_zip(file_record: FileModel) -> bool:
    name = _relative_name(file_record).lower()
    return name.endswith(".zip") and ("sdf" in name or "molecule" in name)


def _candidate_name(base_name: str, record_index: int, record_count: int) -> str:
    if record_count <= 1:
        return base_name
    path = Path(base_name)
    stem = path.stem or "molecule"
    suffix = path.suffix or ".sdf"
    parent = path.parent.as_posix()
    filename = f"{stem}_{record_index}{suffix}"
    return filename if parent == "." else f"{parent}/{filename}"


def _extract_candidates_from_sdf_file(
    file_record: FileModel,
    *,
    next_global_index: int,
) -> list[MoleculeCandidate]:
    if not file_record.storage_path or not Path(file_record.storage_path).exists():
        return []

    text = Path(file_record.storage_path).read_text(encoding="utf-8", errors="replace")
    records = split_sdf_records(text)
    base_name = _relative_name(file_record)

    return [
        MoleculeCandidate(
            source_file_id=str(file_record.id),
            source_filename=file_record.filename,
            sdf_file=_candidate_name(base_name, index, len(records)),
            record_index=index,
            global_index=next_global_index + index,
            sdf_record=record,
        )
        for index, record in enumerate(records)
    ]


def _extract_candidates_from_zip_file(
    file_record: FileModel,
    *,
    next_global_index: int,
) -> list[MoleculeCandidate]:
    if not file_record.storage_path or not Path(file_record.storage_path).exists():
        return []

    candidates: list[MoleculeCandidate] = []
    with zipfile.ZipFile(file_record.storage_path) as archive:
        for member_name in sorted(archive.namelist()):
            if member_name.endswith("/") or not member_name.lower().endswith(".sdf"):
                continue
            text = archive.read(member_name).decode("utf-8", errors="replace")
            records = split_sdf_records(text)
            for record_index, record in enumerate(records):
                candidates.append(
                    MoleculeCandidate(
                        source_file_id=str(file_record.id),
                        source_filename=file_record.filename,
                        sdf_file=_candidate_name(member_name, record_index, len(records)),
                        record_index=record_index,
                        global_index=next_global_index + len(candidates),
                        sdf_record=record,
                    )
                )

    return candidates


def extract_molecule_candidates(output_files: list[FileModel]) -> list[MoleculeCandidate]:
    """从任务输出文件中提取全部 SDF 分子候选。"""
    candidates: list[MoleculeCandidate] = []
    for file_record in output_files:
        if _is_sdf_file(file_record):
            candidates.extend(
                _extract_candidates_from_sdf_file(
                    file_record,
                    next_global_index=len(candidates),
                )
            )
        elif _is_sdf_zip(file_record):
            candidates.extend(
                _extract_candidates_from_zip_file(
                    file_record,
                    next_global_index=len(candidates),
                )
            )
    return candidates


def _rdkit_sa_score(mol: Any) -> float | None:
    try:
        from rdkit.Contrib.SA_Score import sascorer  # type: ignore
    except Exception as exc:
        logger.debug("RDKit SA scorer unavailable: %s", exc)
        return None

    try:
        return float(sascorer.calculateScore(mol))
    except Exception as exc:
        logger.debug("RDKit SA scoring failed: %s", exc)
        return None


def score_molecule_descriptors(candidate: MoleculeCandidate) -> DescriptorScores:
    """使用 RDKit 计算 QED/SA；缺依赖时返回错误而不打断任务。"""
    try:
        from rdkit import Chem  # type: ignore
        from rdkit.Chem import QED  # type: ignore
    except Exception:
        return DescriptorScores(error="RDKit unavailable")

    mol = Chem.MolFromMolBlock(candidate.sdf_record, sanitize=True, removeHs=False)
    if mol is None:
        return DescriptorScores(error="Invalid SDF molecule")

    smiles = Chem.MolToSmiles(mol) or None
    try:
        qed = float(QED.qed(mol))
    except Exception:
        qed = None

    sa = _rdkit_sa_score(mol)
    error = None if sa is not None else "SA scorer unavailable"
    return DescriptorScores(smiles=smiles, qed=qed, sa=sa, error=error)


def _find_receptor_file(input_files: list[FileModel]) -> Path | None:
    preferred: list[FileModel] = []
    fallback: list[FileModel] = []
    for file_record in input_files:
        if not file_record.storage_path:
            continue
        path = Path(file_record.storage_path)
        if not path.exists() or path.suffix.lower() not in {".pdb", ".ent"}:
            continue
        name = (file_record.filename + " " + _relative_name(file_record)).lower()
        if any(token in name for token in ("protein", "receptor", "pocket")):
            preferred.append(file_record)
        else:
            fallback.append(file_record)

    selected = (preferred or fallback)[0] if (preferred or fallback) else None
    return Path(selected.storage_path) if selected and selected.storage_path else None


def _convert_candidate_to_pdb(candidate: MoleculeCandidate, output_path: Path) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".sdf", delete=False) as source_file:
        source_file.write(candidate.sdf_record)
        source_path = Path(source_file.name)

    try:
        command = ["obabel", "-isdf", str(source_path), "-opdb", "-O", str(output_path)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    finally:
        source_path.unlink(missing_ok=True)

    if result.returncode != 0 or not output_path.exists():
        message = (result.stderr or result.stdout or "OpenBabel conversion failed").strip()
        raise RuntimeError(message)


def score_molecule_vina(candidate: MoleculeCandidate, receptor_path: Path | None) -> float | None:
    """使用 Vina 对接评分；没有受体或工具链时跳过。"""
    if receptor_path is None or not shutil.which("vina") or not shutil.which("obabel"):
        return None

    from app.agents.aidd.builtin_tools import run_vina_docking_with_tool

    with tempfile.TemporaryDirectory(prefix="molecule-scoring-") as tmp_dir:
        ligand_path = Path(tmp_dir) / "ligand.pdb"
        _convert_candidate_to_pdb(candidate, ligand_path)
        report = run_vina_docking_with_tool(receptor_path, ligand_path)
        score = report.get("vina_score")
        return float(score) if isinstance(score, (int, float)) else None


def _composite_score(qed: float | None, sa: float | None, vina_score: float | None) -> float:
    qed_norm = max(0.0, min(1.0, qed if qed is not None else 0.0))
    sa_norm = max(0.0, min(1.0, (10.0 - sa) / 9.0)) if sa is not None else 0.0
    vina_norm = max(0.0, min(1.0, -vina_score / 12.0)) if vina_score is not None else 0.0
    if vina_score is not None:
        return round(vina_norm * 0.6 + qed_norm * 0.3 + sa_norm * 0.1, 6)
    return round(qed_norm * 0.7 + sa_norm * 0.3, 6)


def _sort_key(score: MoleculeScore) -> tuple[float, float, float, int]:
    if score.vina_score is not None:
        return (0.0, score.vina_score, -(score.qed if score.qed is not None else -math.inf), score.candidate.global_index)
    return (
        1.0,
        -(score.qed if score.qed is not None else -math.inf),
        score.sa if score.sa is not None else math.inf,
        score.candidate.global_index,
    )


def score_candidates(
    candidates: list[MoleculeCandidate],
    *,
    receptor_path: Path | None,
) -> list[MoleculeScore]:
    scores: list[MoleculeScore] = []
    for candidate in candidates:
        descriptor = score_molecule_descriptors(candidate)
        vina_score: float | None = None
        error = descriptor.error

        try:
            vina_score = score_molecule_vina(candidate, receptor_path)
        except Exception as exc:
            logger.warning("Vina scoring failed for %s: %s", candidate.sdf_file, exc)
            error = "; ".join(part for part in (error, f"Vina failed: {exc}") if part)

        scores.append(
            MoleculeScore(
                candidate=candidate,
                smiles=descriptor.smiles,
                qed=descriptor.qed,
                sa=descriptor.sa,
                vina_score=vina_score,
                composite_score=_composite_score(descriptor.qed, descriptor.sa, vina_score),
                error=error,
            )
        )

    return sorted(scores, key=_sort_key)


def _csv_value(value: float | str | int | None) -> str | float | int:
    if value is None:
        return ""
    if isinstance(value, float):
        return round(value, 6)
    return value


def build_scores_csv(scores: list[MoleculeScore]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["rank", "index", "smiles", "sdf_file", "qed", "sa", "vina_score", "composite_score", "error"])
    for rank, score in enumerate(scores, start=1):
        writer.writerow(
            [
                rank,
                score.candidate.record_index,
                score.smiles or "",
                score.candidate.sdf_file,
                _csv_value(score.qed),
                _csv_value(score.sa),
                _csv_value(score.vina_score),
                _csv_value(score.composite_score),
                score.error or "",
            ]
        )
    return output.getvalue().encode("utf-8")


def build_top_sdf(scores: list[MoleculeScore], limit: int = TOP_MOLECULE_LIMIT) -> bytes:
    content = "".join(score.candidate.sdf_record for score in scores[:limit])
    return content.encode("utf-8")


async def _load_files_by_ids(db: AsyncSession, file_ids: list[str]) -> list[FileModel]:
    if not file_ids:
        return []

    result = await db.execute(select(FileModel).where(FileModel.id.in_(file_ids)))
    files = {str(file.id): file for file in result.scalars().all()}
    return [files[file_id] for file_id in file_ids if file_id in files]


async def _load_input_files(db: AsyncSession, task: Task) -> list[FileModel]:
    input_result = await db.execute(select(TaskInput).where(TaskInput.task_id == task.id))
    task_input = input_result.scalar_one_or_none()
    input_ids = task_input.file_ids if task_input and isinstance(task_input.file_ids, list) else []
    return await _load_files_by_ids(db, [str(file_id) for file_id in input_ids if file_id])


async def _load_tool(db: AsyncSession, task: Task) -> Tool | None:
    if not task.tool_id:
        return None
    return await db.get(Tool, str(task.tool_id))


def _capability_from_config(config: dict[str, Any]) -> str | None:
    raw_capability = config.get("agent_capability")
    if isinstance(raw_capability, dict) and raw_capability.get("enabled") is True:
        return str(raw_capability.get("capability") or "")
    if isinstance(raw_capability, str):
        return raw_capability
    return None


def _config_outputs_generated_ligand(config: dict[str, Any]) -> bool:
    raw_capability = config.get("agent_capability")
    outputs = raw_capability.get("outputs") if isinstance(raw_capability, dict) else None
    if not isinstance(outputs, list):
        outputs = config.get("agent_outputs")
    if not isinstance(outputs, list):
        return False
    return any(
        isinstance(item, dict) and item.get("semantic_type") == "generated_ligand"
        for item in outputs
    )


def _is_molecule_generation_tool(tool_version: ToolVersion, tool: Tool | None) -> bool:
    config = tool_version.config if isinstance(tool_version.config, dict) else {}
    if _capability_from_config(config) == "molecule_generation":
        return True
    if _config_outputs_generated_ligand(config):
        return True

    if tool:
        try:
            from app.agents.aidd.capabilities import AIDD_TOOL_CAPABILITIES

            capability = AIDD_TOOL_CAPABILITIES.get(tool.slug)
            return bool(capability and capability.capability == "molecule_generation")
        except Exception as exc:
            logger.debug(
                "Failed to resolve AIDD capability for tool %s: %s",
                tool.slug,
                exc,
            )
            return False
    return False


def _output_ids(output_result: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    direct_ids = output_result.get("output_file_ids")
    if isinstance(direct_ids, list):
        ids.extend(str(file_id) for file_id in direct_ids if file_id)

    nested = output_result.get("result")
    if isinstance(nested, dict) and isinstance(nested.get("output_file_ids"), list):
        ids.extend(str(file_id) for file_id in nested["output_file_ids"] if file_id)

    deduped: list[str] = []
    seen: set[str] = set()
    for file_id in ids:
        if file_id in seen:
            continue
        seen.add(file_id)
        deduped.append(file_id)
    return deduped


def _merge_output_ids(output_result: dict[str, Any], file_ids: list[str]) -> None:
    deduped: list[str] = []
    seen: set[str] = set()
    for file_id in [*_output_ids(output_result), *file_ids]:
        if file_id in seen:
            continue
        seen.add(file_id)
        deduped.append(file_id)

    output_result["output_file_ids"] = deduped
    nested = output_result.get("result")
    if isinstance(nested, dict):
        nested["output_file_ids"] = deduped


async def _store_artifact(
    db: AsyncSession,
    *,
    task: Task,
    filename: str,
    content: bytes,
    relative_path: str,
) -> FileModel:
    file_hash = hashlib.sha256(content).hexdigest()
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if filename.endswith(".sdf"):
        content_type = "chemical/x-mdl-sdfile"
    elif filename.endswith(".csv"):
        content_type = "text/csv"

    file_id = str(uuid.uuid4())
    storage_path = get_file_path(file_id, filename)
    file_record = FileModel(
        id=file_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(content),
        sha256=file_hash,
        storage_path=str(storage_path),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        owner_id=task.user_id,
        session_id=task.session_id,
        is_public=False,
        is_permanent=False,
        file_meta={
            "relative_path": relative_path,
            "original_name": filename,
            "generated_by": "molecule_scoring",
        },
    )
    db.add(file_record)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(content)
    await db.flush()
    return file_record


def _summary(scores: list[MoleculeScore], receptor_path: Path | None) -> dict[str, Any]:
    errors = [score.error for score in scores if score.error]
    return {
        "enabled": True,
        "candidate_count": len(scores),
        "top_count": min(TOP_MOLECULE_LIMIT, len(scores)),
        "ranking": "vina_score asc, qed desc, sa asc",
        "vina_enabled": receptor_path is not None,
        "qed_count": sum(1 for score in scores if score.qed is not None),
        "sa_count": sum(1 for score in scores if score.sa is not None),
        "vina_count": sum(1 for score in scores if score.vina_score is not None),
        "errors": errors[:10],
    }


async def append_molecule_scoring_artifacts(
    db: AsyncSession,
    task: Task,
    tool_version: ToolVersion,
    output_result: dict[str, Any],
) -> dict[str, Any]:
    """如果是分子生成任务，则追加评分 CSV 和 Top10 SDF 到输出。"""
    tool = await _load_tool(db, task)
    if not _is_molecule_generation_tool(tool_version, tool):
        return output_result

    output_file_ids = _output_ids(output_result)
    output_files = await _load_files_by_ids(db, output_file_ids)
    candidates = extract_molecule_candidates(output_files)
    if not candidates:
        return output_result

    input_files = await _load_input_files(db, task)
    receptor_path = _find_receptor_file(input_files)
    scores = score_candidates(candidates, receptor_path=receptor_path)
    if not scores:
        return output_result

    score_csv = await _store_artifact(
        db,
        task=task,
        filename=SCORE_CSV_NAME,
        content=build_scores_csv(scores),
        relative_path=f"artifacts/{SCORE_CSV_NAME}",
    )
    top_sdf = await _store_artifact(
        db,
        task=task,
        filename=TOP_SDF_NAME,
        content=build_top_sdf(scores),
        relative_path=f"artifacts/{TOP_SDF_NAME}",
    )

    _merge_output_ids(output_result, [str(score_csv.id), str(top_sdf.id)])
    summary = _summary(scores, receptor_path)
    nested = output_result.get("result")
    if isinstance(nested, dict):
        nested["molecule_scoring"] = summary
    else:
        output_result["molecule_scoring"] = summary

    logger.info(
        "Molecule scoring appended %s and %s for task %s: %s",
        SCORE_CSV_NAME,
        TOP_SDF_NAME,
        task.id,
        json.dumps(summary, ensure_ascii=False),
    )
    return output_result
