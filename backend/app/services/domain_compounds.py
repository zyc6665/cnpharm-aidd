"""Shared domain logic for compounds, candidates and candidate sets (docs/04 §7).

三个概念的服务边界：

``compounds``
    全局去重主表，服务层负责「同分子只留一行」——``upsert_compound`` 按 InChIKey
    先查后写，命中即复用并（可选）刷新派生性质。
``candidates``
    项目内候选物，写入时校验配额 ``MAX_PROJECT_CANDIDATES``（docs/04 §5.7）。
``candidate_sets``
    集合与集合项，``item_count`` 在同一事务内维护；更新走乐观锁
    （``UPDATE ... WHERE id=? AND version=?``，影响行数 0 → ``ConflictException``）。

指纹（``molecule_fingerprints``）在这里统一落库：主键即 ``compound_id``，重复计算
用「先查后插」而不是 ``ON CONFLICT``，因为 SQLAlchemy 的跨方言 upsert 支持不一致，
而这里并发冲突概率极低（同一分子被两个请求同时首次导入），冲突时让第二次写入
走 ``IntegrityError`` 兜底即可。
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select, update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.chemistry.molecule_properties import (
    describe_smiles,
    fingerprints_of,
    inchikey_of,
    tanimoto_from_bytes,
)
from app.common.exceptions import (
    ConflictException,
    NotFoundException,
    QuotaExceededException,
    ValidationException,
)
from app.common.time import utcnow
from app.config import settings
from app.models.compounds import (
    CANDIDATE_TYPE_PEPTIDE,
    CANDIDATE_TYPE_SMALL_MOLECULE,
    Candidate,
    CandidateSet,
    CandidateSetItem,
    Compound,
    MoleculeFingerprint,
)
from app.models.projects import Project
from app.models.users import User
from app.services.project_access import load_project_membership, require_project_role

WRITE_ROLES = ("owner", "editor")
READ_ROLES = ("owner", "editor", "runner", "viewer")

#: 单次导入的化合物行数上限。与文件大小上限互补：200MB 的 SDF 可能有几十万条，
#: 一期不做流式解析，因此显式限一个行数，超限直接要求拆分文件。
MAX_IMPORT_ROWS = 50000


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _number(value: Any) -> Any:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def serialize_compound(compound: Compound) -> dict:
    return {
        "id": compound.id,
        "name": compound.name,
        "inchikey": compound.inchikey,
        "canonical_smiles": compound.canonical_smiles,
        "mol_formula": compound.mol_formula,
        "mol_weight": _number(compound.mol_weight),
        "props": compound.props or {},
        "structure_urn": compound.structure_urn,
        "created_by": compound.created_by,
        "created_at": _iso(compound.created_at),
        "updated_at": _iso(compound.updated_at),
    }


def serialize_candidate(candidate: Candidate, *, compound: Compound | None = None) -> dict:
    """Serialize a candidate, folding in the compound when it is a small molecule.

    前端候选物列表要同时显示 2D 结构、SMILES、MW、logP、QED（PRD M3-AC），这些
    都在 compound 上；把它们内联进候选物响应，避免每个候选物再发一次请求。
    """
    data = {
        "id": candidate.id,
        "project_id": candidate.project_id,
        "candidate_type": candidate.candidate_type,
        "compound_id": candidate.compound_id,
        "peptide_sequence": candidate.peptide_sequence,
        "name": candidate.name,
        "code": candidate.code,
        "source": candidate.source,
        "design_score": _number(candidate.design_score),
        "task_id": candidate.task_id,
        "attrs": candidate.attrs or {},
        "created_at": _iso(candidate.created_at),
        "updated_at": _iso(candidate.updated_at),
        "compound": serialize_compound(compound) if compound is not None else None,
    }
    return data


def serialize_candidate_set(candidate_set: CandidateSet) -> dict:
    return {
        "id": candidate_set.id,
        "project_id": candidate_set.project_id,
        "name": candidate_set.name,
        "description": candidate_set.description,
        "item_count": candidate_set.item_count,
        "source_task_id": candidate_set.source_task_id,
        "version": candidate_set.version,
        "is_archived": bool(candidate_set.is_archived),
        "created_at": _iso(candidate_set.created_at),
        "updated_at": _iso(candidate_set.updated_at),
    }


def serialize_set_item(item: CandidateSetItem, candidate: Candidate | None) -> dict:
    location = "compound" if candidate is not None else "peptide"
    return {
        "id": item.id,
        "set_id": item.set_id,
        "candidate_id": item.candidate_id,
        "ordinal": item.ordinal,
        "snapshot_score": _number(item.snapshot_score),
        "candidate": serialize_candidate(candidate) if candidate is not None else None,
        "location": location,
    }


# ---------------------------------------------------------------------------
# Compounds
# ---------------------------------------------------------------------------


async def load_compound(db: AsyncSession, compound_id: str) -> Compound:
    compound = await db.get(Compound, compound_id)
    if compound is None:
        raise NotFoundException("化合物不存在")
    return compound


async def find_compound_by_inchikey(db: AsyncSession, inchikey: str) -> Compound | None:
    result = await db.execute(select(Compound).where(Compound.inchikey == inchikey))
    return result.scalar_one_or_none()


async def upsert_compound(
    db: AsyncSession,
    *,
    smiles: str,
    name: str | None,
    user: User,
    refresh_descriptors: bool = False,
) -> tuple[Compound, bool]:
    """Insert or reuse a compound by InChIKey. Returns ``(compound, created)``.

    ``refresh_descriptors=True`` 会在复用时用最新的 RDKit 重算 ``props``——升级
    RDKit 之后跑一次导入即可刷新全部派生性质，不需要单独的批处理脚本。
    """
    descriptor = describe_smiles(smiles)
    existing = await find_compound_by_inchikey(db, descriptor.inchikey)
    if existing is not None:
        if refresh_descriptors:
            existing.props = descriptor.props
            existing.mol_formula = descriptor.mol_formula or existing.mol_formula
            existing.mol_weight = descriptor.mol_weight or existing.mol_weight
            existing.canonical_smiles = descriptor.canonical_smiles
        if name and not existing.name:
            existing.name = name
        await db.flush()
        return existing, False

    compound = Compound(
        created_by=str(user.id),
        name=name,
        inchikey=descriptor.inchikey,
        canonical_smiles=descriptor.canonical_smiles,
        mol_formula=descriptor.mol_formula,
        mol_weight=descriptor.mol_weight,
        props=descriptor.props,
    )
    db.add(compound)
    await db.flush()
    # 指纹在写入时一次算好：相似性检索是全表扫描 + 应用内 Tanimoto，缺指纹的分子
    # 会直接从结果里消失（M1 的「按 IP 相似性找已知分子」就永远查不到新分子）。
    await ensure_fingerprint(db, compound)
    return compound, True


async def ensure_fingerprint(db: AsyncSession, compound: Compound) -> MoleculeFingerprint:
    """Return the cached fingerprint row, computing it the first time.

    指纹是缓存而不是真值，所以 ``computed_at`` 只是诊断信息；重算不会让历史结果
    失效（相似性查询每次都是现算 Tanimoto）。
    """
    existing = await db.get(MoleculeFingerprint, compound.id)
    if existing is not None and existing.fp_ecfp4:
        return existing
    payload = fingerprints_of(compound.canonical_smiles)
    if existing is None:
        existing = MoleculeFingerprint(
            compound_id=compound.id,
            fp_ecfp4=payload.fp_ecfp4,
            fp_maccs=payload.fp_maccs,
            fp_ecfp4_bits=payload.fp_ecfp4_bits,
            rdkit_version=payload.rdkit_version,
            computed_at=utcnow(),
        )
        db.add(existing)
    else:
        existing.fp_ecfp4 = payload.fp_ecfp4
        existing.fp_maccs = payload.fp_maccs
        existing.fp_ecfp4_bits = payload.fp_ecfp4_bits
        existing.rdkit_version = payload.rdkit_version
        existing.computed_at = utcnow()
    try:
        await db.flush()
    except IntegrityError:  # pragma: no cover - 并发首次导入同一分子的兜底
        await db.rollback()
        raise ConflictException("分子指纹并发写入冲突，请重试")
    return existing


@dataclass
class ImportOutcome:
    """批量导入的累计结果（对应 docs/05 §4.1 的 ``summary``）。"""

    total: int = 0
    success: int = 0
    failed: int = 0
    duplicate: int = 0
    created_compounds: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    def add_error(self, row: int, message: str) -> None:
        # 只保留前 500 条，异常清单本身也要能塞进一次响应（M1-BR-2）。
        if len(self.errors) < 500:
            self.errors.append({"row": row, "message": message})

    def summary(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "duplicate": self.duplicate,
            "created_compounds": self.created_compounds,
        }


@dataclass(frozen=True)
class ImportRow:
    row_number: int
    smiles: str
    name: str | None


def _normalize_header(value: str) -> str:
    return (value or "").strip().lower().replace(" ", "_")


def parse_compound_rows(
    content: bytes,
    *,
    filename: str,
    smiles_column: str | None = None,
    name_column: str | None = None,
) -> list[ImportRow]:
    """Parse an uploaded molecule file into ``(row_number, smiles, name)`` tuples.

    支持 SMILES / CSV / TSV / SDF 四类（PRD M1-FR-03 还要求 .mol/.mol2，那是
    单分子文件，走的是 ``POST /compounds`` 而不是批量导入）。行号从 1 开始且指
    **数据行**，与「导入异常清单可定位行号」的验收口径一致。
    """
    text = content.decode("utf-8-sig", errors="replace")
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if suffix in {"sdf", "sd"}:
        return _parse_sdf_rows(text)
    if suffix in {"csv", "tsv"} or _looks_like_delimited(text):
        return _parse_delimited_rows(
            text, smiles_column=smiles_column, name_column=name_column, suffix=suffix
        )
    return _parse_smiles_rows(text)


def _looks_like_delimited(text: str) -> bool:
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    header = first_line.lower()
    return ("," in first_line or "\t" in first_line) and "smiles" in header


def _parse_delimited_rows(
    text: str,
    *,
    smiles_column: str | None,
    name_column: str | None,
    suffix: str,
) -> list[ImportRow]:
    delimiter = "\t" if suffix == "tsv" or ("\t" in text.splitlines()[0] and "," not in text.splitlines()[0]) else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    fieldnames = list(reader.fieldnames or [])
    if not fieldnames:
        raise ValidationException("文件为空或缺少表头")

    normalized = {_normalize_header(name): name for name in fieldnames}
    smiles_field = (
        normalized.get(_normalize_header(smiles_column)) if smiles_column else None
    ) or normalized.get("smiles") or normalized.get("smi") or normalized.get("canonical_smiles")
    if not smiles_field:
        raise ValidationException("文件中未找到 SMILES 列")
    name_field = (
        (normalized.get(_normalize_header(name_column)) if name_column else None)
        or normalized.get("name")
        or normalized.get("id")
        or normalized.get("molecule_id")
    )

    rows: list[ImportRow] = []
    for index, row in enumerate(reader, start=1):
        smiles = str(row.get(smiles_field) or "").strip()
        if not smiles:
            continue
        rows.append(
            ImportRow(
                row_number=index,
                smiles=smiles,
                name=str(row.get(name_field) or "").strip() if name_field else None,
            )
        )
    return rows


def _parse_smiles_rows(text: str) -> list[ImportRow]:
    rows: list[ImportRow] = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        smiles = parts[0].strip()
        if not smiles:
            continue
        # 首行若是 `smiles` / `smiles name` 表头则跳过，避免把表头当分子。
        if not rows and smiles.lower() in {"smiles", "smi", "canonical_smiles", "smiles,name"}:
            continue
        rows.append(
            ImportRow(
                row_number=index,
                smiles=smiles,
                name=parts[1].strip() if len(parts) > 1 else None,
            )
        )
    return rows


def _parse_sdf_rows(text: str) -> list[ImportRow]:
    """Extract molecules from SDF by taking the first ``M  END`` block per record.

    只取 SMILES：SDF 也能提供坐标，但一期把「结构 → SMILES → 规范化」作为唯一
    入库路径，避免同一分子有「按坐标入库」和「按 SMILES 入库」两种身份判定。
    """
    from rdkit import Chem

    rows: list[ImportRow] = []
    for index, block in enumerate(text.split("$$$$"), start=1):
        block = block.strip("\r\n")
        if not block.strip():
            continue
        molecule = Chem.MolFromMolBlock(block, sanitize=True, removeHs=False)
        if molecule is None:
            rows.append(ImportRow(row_number=index, smiles="", name=None))
            continue
        name = block.splitlines()[0].strip() if block.splitlines() else None
        rows.append(
            ImportRow(
                row_number=index,
                smiles=Chem.MolToSmiles(molecule),
                name=name or None,
            )
        )
    return rows


async def import_compounds(
    db: AsyncSession,
    *,
    project: Project,
    user: User,
    content: bytes,
    filename: str,
    smiles_column: str | None = None,
    name_column: str | None = None,
    dedupe_strategy: str = "INCHIKEY_SKIP",
    on_error: str = "SKIP_AND_CONTINUE",
) -> ImportOutcome:
    """Import a molecule library file, returning the summary and per-row errors."""
    rows = parse_compound_rows(
        content, filename=filename, smiles_column=smiles_column, name_column=name_column
    )
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValidationException(
            f"单次导入最多 {MAX_IMPORT_ROWS} 条分子，当前 {len(rows)} 条，请拆分文件"
        )

    outcome = ImportOutcome(total=len(rows))
    for row in rows:
        if not row.smiles:
            outcome.failed += 1
            outcome.add_error(row.row_number, "SDF 结构无法解析")
            if on_error == "ABORT":
                break
            continue
        try:
            compound, created = await upsert_compound(
                db,
                smiles=row.smiles,
                name=row.name,
                user=user,
                refresh_descriptors=dedupe_strategy == "INCHIKEY_UPDATE",
            )
        except ValidationException as exc:
            outcome.failed += 1
            outcome.add_error(row.row_number, str(exc))
            if on_error == "ABORT":
                break
            continue

        if created:
            outcome.created_compounds += 1
            outcome.success += 1
        elif dedupe_strategy == "INCHIKEY_ERROR":
            outcome.duplicate += 1
            outcome.add_error(row.row_number, f"分子已存在（InChIKey {compound.inchikey}）")
            if on_error == "ABORT":
                break
        else:
            # SKIP / UPDATE 都算「已覆盖」，不算失败——验收口径的成功率只统计
            # 结构性失败（无法解析的 SMILES），去重命中不是错误。
            outcome.duplicate += 1
            outcome.success += 1

    return outcome


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


async def load_candidate(db: AsyncSession, candidate_id: str) -> Candidate:
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise NotFoundException("候选物不存在")
    return candidate


async def load_candidate_with_compound(
    db: AsyncSession, candidate_id: str
) -> tuple[Candidate, Compound | None]:
    candidate = await load_candidate(db, candidate_id)
    compound = None
    if candidate.compound_id:
        compound = await db.get(Compound, candidate.compound_id)
    return candidate, compound


async def require_candidate_write_access(
    db: AsyncSession, *, candidate: Candidate, user: User
) -> None:
    await require_project_role(
        db,
        project_id=str(candidate.project_id),
        user=user,
        allowed_roles=WRITE_ROLES,
    )


async def require_candidate_read_access(
    db: AsyncSession, *, candidate: Candidate, user: User
) -> None:
    await load_project_membership(db, project_id=str(candidate.project_id), user_id=str(user.id))


async def count_project_candidates(db: AsyncSession, *, project_id: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(Candidate).where(Candidate.project_id == project_id)
    )
    return int(result.scalar() or 0)


async def ensure_candidate_quota(db: AsyncSession, *, project_id: str, incoming: int = 1) -> None:
    """Enforce ``MAX_PROJECT_CANDIDATES`` (docs/04 §5.7)."""
    limit = int(getattr(settings, "MAX_PROJECT_CANDIDATES", 20000) or 20000)
    current = await count_project_candidates(db, project_id=project_id)
    if current + incoming > limit:
        raise QuotaExceededException(
            f"项目候选物数量已达上限 {limit}，请归档旧候选集或联系管理员调整配额"
        )


async def create_candidate(
    db: AsyncSession,
    *,
    project: Project,
    user: User,
    candidate_type: str,
    smiles: str | None,
    peptide_sequence: str | None,
    name: str | None,
    code: str | None,
    source: str,
    design_score: float | None,
    task_id: str | None,
    attrs: dict[str, Any] | None,
) -> Candidate:
    await ensure_candidate_quota(db, project_id=str(project.id))

    compound_id = None
    if candidate_type == CANDIDATE_TYPE_SMALL_MOLECULE:
        if not smiles:
            raise ValidationException("小分子候选物必须提供 smiles")
        compound, _ = await upsert_compound(
            db, smiles=smiles, name=name, user=user, refresh_descriptors=False
        )
        compound_id = compound.id
    elif candidate_type == CANDIDATE_TYPE_PEPTIDE:
        if not (peptide_sequence or "").strip():
            raise ValidationException("多肽候选物必须提供 peptide_sequence")
        peptide_sequence = peptide_sequence.strip()
    else:
        raise ValidationException(f"不支持的候选物类型: {candidate_type}")

    candidate = Candidate(
        project_id=str(project.id),
        created_by=str(user.id),
        candidate_type=candidate_type,
        compound_id=compound_id,
        peptide_sequence=peptide_sequence,
        name=name,
        code=code,
        source=source,
        design_score=design_score,
        task_id=task_id,
        attrs=attrs or {},
    )
    db.add(candidate)
    await db.flush()
    return candidate


# ---------------------------------------------------------------------------
# Candidate sets
# ---------------------------------------------------------------------------


async def load_candidate_set(db: AsyncSession, set_id: str) -> CandidateSet:
    candidate_set = await db.get(CandidateSet, set_id)
    if candidate_set is None:
        raise NotFoundException("候选集不存在")
    return candidate_set


async def require_set_write_access(
    db: AsyncSession, *, candidate_set: CandidateSet, user: User
) -> None:
    await require_project_role(
        db,
        project_id=str(candidate_set.project_id),
        user=user,
        allowed_roles=WRITE_ROLES,
    )


async def require_set_read_access(
    db: AsyncSession, *, candidate_set: CandidateSet, user: User
) -> None:
    await load_project_membership(
        db, project_id=str(candidate_set.project_id), user_id=str(user.id)
    )


async def update_candidate_set(
    db: AsyncSession,
    *,
    candidate_set: CandidateSet,
    expected_version: int,
    name: str | None = None,
    description: str | None = None,
) -> CandidateSet:
    """Optimistic-lock update of a candidate set (docs/04 §5.6, 40903)."""
    # 先取出主键：冲突分支里要 rollback，rollback 会让 ORM 实例过期，之后再读
    # 属性会触发隐式 IO 并抛 MissingGreenlet。
    set_id = str(candidate_set.id)
    values: dict[str, Any] = {"version": expected_version + 1, "updated_at": utcnow()}
    if name is not None:
        values["name"] = name
    if description is not None:
        values["description"] = description

    result = await db.execute(
        sa_update(CandidateSet)
        .where(CandidateSet.id == set_id, CandidateSet.version == expected_version)
        .values(**values)
    )
    if result.rowcount == 0:
        await db.rollback()
        current = await load_candidate_set(db, set_id)
        raise ConflictException(
            "候选集已被其他人修改，请刷新后重试",
            detail={"currentVersion": current.version},
        )
    await db.flush()
    return await load_candidate_set(db, set_id)


async def add_set_items(
    db: AsyncSession,
    *,
    candidate_set: CandidateSet,
    candidate_ids: Sequence[str],
    snapshot_score: float | None = None,
) -> tuple[list[CandidateSetItem], int]:
    """Append candidates to a set, skipping ones already present.

    Returns ``(inserted_items, skipped_count)``. 幂等由 ``(set_id, candidate_id)``
    唯一约束保证，但这里先查一次已存在的再插入，避免整批因一条重复而回滚。
    """
    if not candidate_ids:
        return [], 0

    existing_result = await db.execute(
        select(CandidateSetItem.candidate_id).where(
            CandidateSetItem.set_id == candidate_set.id,
            CandidateSetItem.candidate_id.in_(list(candidate_ids)),
        )
    )
    existing_ids = {row[0] for row in existing_result.all()}

    candidates_result = await db.execute(
        select(Candidate).where(Candidate.id.in_(list(candidate_ids)))
    )
    candidates = {item.id: item for item in candidates_result.scalars().all()}

    next_ordinal = int(candidate_set.item_count or 0)
    inserted: list[CandidateSetItem] = []
    skipped = 0
    for candidate_id in candidate_ids:
        if candidate_id in existing_ids or candidate_id not in candidates:
            skipped += 1
            continue
        candidate = candidates[candidate_id]
        if candidate.project_id != candidate_set.project_id:
            raise ValidationException("候选物不属于该候选集所在项目")
        score = snapshot_score
        if score is None and candidate.design_score is not None:
            score = float(candidate.design_score)
        item = CandidateSetItem(
            set_id=candidate_set.id,
            candidate_id=candidate_id,
            ordinal=next_ordinal,
            snapshot_score=score,
        )
        next_ordinal += 1
        db.add(item)
        inserted.append(item)

    if inserted:
        candidate_set.item_count = next_ordinal
        candidate_set.version = int(candidate_set.version or 1) + 1
    await db.flush()
    return inserted, skipped


# ---------------------------------------------------------------------------
# Similarity search
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimilarityHit:
    compound: Compound
    similarity: float


async def search_similar(
    db: AsyncSession, *, smiles: str, limit: int = 20, threshold: float = 0.0
) -> list[SimilarityHit]:
    """Tanimoto similarity search over the whole compound table (docs/04 §5.7).

    一期是全表扫描 + 应用内 Tanimoto：2 万条 × 2048bit ≈ 5MB 内存，全扫 <200ms。
    超过 ``MAX_PROJECT_CANDIDATES`` 量级必须换专用索引或外部检索服务（二期）。
    """
    query_payload = fingerprints_of(smiles)
    result = await db.execute(
        select(Compound, MoleculeFingerprint)
        .join(MoleculeFingerprint, MoleculeFingerprint.compound_id == Compound.id)
        .where(MoleculeFingerprint.fp_ecfp4.is_not(None))
    )
    hits: list[SimilarityHit] = []
    for compound, fingerprint in result.all():
        if not fingerprint.fp_ecfp4:
            continue
        score = tanimoto_from_bytes(query_payload.fp_ecfp4, fingerprint.fp_ecfp4)
        if score >= threshold:
            hits.append(SimilarityHit(compound=compound, similarity=score))
    hits.sort(key=lambda item: item.similarity, reverse=True)
    return hits[: max(1, min(int(limit), 200))]


async def backfill_fingerprints(
    db: AsyncSession, *, compounds: Iterable[Compound] | None = None
) -> int:
    """Compute missing fingerprints; returns how many rows were written.

    用于「升级 RDKit」或「历史数据从别的系统迁进来」之后的一次性补齐。默认扫
    全部没有指纹的化合物，也可以传入指定集合。
    """
    if compounds is None:
        result = await db.execute(
            select(Compound)
            .outerjoin(MoleculeFingerprint, MoleculeFingerprint.compound_id == Compound.id)
            .where(MoleculeFingerprint.compound_id.is_(None))
        )
        targets = list(result.scalars().all())
    else:
        targets = list(compounds)

    written = 0
    for compound in targets:
        await ensure_fingerprint(db, compound)
        written += 1
    return written


# ---------------------------------------------------------------------------
# Comparison (M3-FR-08)
# ---------------------------------------------------------------------------


async def compare_candidates(
    db: AsyncSession, *, project_id: str, candidate_ids: Sequence[str]
) -> list[dict[str, Any]]:
    """Load up to six candidates for side-by-side comparison.

    差异高亮由前端做（它已经拿到全部字段）；服务端只保证顺序与请求一致，并把
    分子性质摊平到顶层，省得前端为每个候选物再取一次 compound。
    """
    if not candidate_ids:
        return []
    result = await db.execute(select(Candidate).where(Candidate.id.in_(list(candidate_ids))))
    candidates = {item.id: item for item in result.scalars().all()}

    missing = [cid for cid in candidate_ids if cid not in candidates]
    if missing:
        raise NotFoundException(f"候选物不存在: {', '.join(missing[:5])}")

    ordered = [candidates[cid] for cid in candidate_ids]
    out_of_project = [item.id for item in ordered if item.project_id != project_id]
    if out_of_project:
        raise ValidationException("候选物不属于当前项目")

    compound_ids = [item.compound_id for item in ordered if item.compound_id]
    compounds: dict[str, Compound] = {}
    if compound_ids:
        compound_result = await db.execute(
            select(Compound).where(Compound.id.in_(compound_ids))
        )
        compounds = {item.id: item for item in compound_result.scalars().all()}

    rows: list[dict[str, Any]] = []
    for candidate in ordered:
        compound = compounds.get(candidate.compound_id) if candidate.compound_id else None
        props = (compound.props or {}) if compound is not None else {}
        rows.append(
            {
                **serialize_candidate(candidate, compound=compound),
                "mol_weight": _number(compound.mol_weight) if compound else None,
                "mol_formula": compound.mol_formula if compound else None,
                "logP": props.get("logP"),
                "TPSA": props.get("TPSA"),
                "HBD": props.get("HBD"),
                "HBA": props.get("HBA"),
                "RotB": props.get("RotB"),
                "QED": props.get("QED"),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Project cascade
# ---------------------------------------------------------------------------


async def delete_project_compound_rows(db: AsyncSession, *, project_id: str) -> None:
    """Delete candidates and candidate sets of a project (called by project delete).

    ``compounds`` 不删：它是全局去重主表，可能被其他项目引用；孤儿化合物由运维
    期的清理作业处理（docs/04 §7.1 把 compound 定义为全平台主数据）。
    """
    from sqlalchemy import delete as sa_delete

    set_ids_result = await db.execute(
        select(CandidateSet.id).where(CandidateSet.project_id == project_id)
    )
    set_ids = [row[0] for row in set_ids_result.all()]
    if set_ids:
        await db.execute(sa_delete(CandidateSetItem).where(CandidateSetItem.set_id.in_(set_ids)))
        await db.execute(sa_delete(CandidateSet).where(CandidateSet.id.in_(set_ids)))
    await db.execute(sa_delete(Candidate).where(Candidate.project_id == project_id))


async def project_compound_counts(db: AsyncSession, *, project_id: str) -> dict[str, int]:
    candidates = await db.execute(
        select(func.count()).select_from(Candidate).where(Candidate.project_id == project_id)
    )
    sets = await db.execute(
        select(func.count()).select_from(CandidateSet).where(CandidateSet.project_id == project_id)
    )
    return {
        "candidates": int(candidates.scalar() or 0),
        "candidate_sets": int(sets.scalar() or 0),
    }


def inchikey_for(smiles: str) -> str:
    """Thin re-export so API layer does not import ``app.chemistry`` directly."""
    return inchikey_of(smiles)
