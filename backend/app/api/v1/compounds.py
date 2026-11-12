"""Compound / candidate / candidate-set APIs (docs/05 §4, §5; docs/01 M1, M3).

端点分两组注册：

- ``project_router``（前缀 ``/projects``）：项目空间的化合物、候选物与候选集集合
- ``router``（无前缀）：单项读取、比较、相似性检索与集合导出

领域逻辑集中在 ``app.services.domain_compounds``，本模块只负责 HTTP 语义、权限
入口与响应包装。
"""

from __future__ import annotations

import csv
import io
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.exceptions import NotFoundException, ValidationException
from app.common.responses import paginated_response, success_response
from app.common.search import DEFAULT_KEYWORD_MAX_LENGTH, LIKE_ESCAPE, like_pattern
from app.config import settings
from app.database.session import get_db
from app.feature_flags import require_feature_flag
from app.files.content import read_file_bytes
from app.files.file_records import is_file_usable, user_can_access_file
from app.files.remote_access_tokens import create_browser_file_access_token
from app.logging.audit import ResourceType
from app.models.compounds import (
    CANDIDATE_TYPE_SMALL_MOLECULE,
    Candidate,
    CandidateSet,
    CandidateSetItem,
    Compound,
)
from app.models.files import File as FileModel
from app.models.projects import Project
from app.models.users import User
from app.schemas.compounds import (
    CandidateCompareRequest,
    CandidateCreate,
    CandidateSetCreate,
    CandidateSetItemsAdd,
    CandidateSetUpdate,
    CandidateUpdate,
    CompoundCreate,
    CompoundImportRequest,
)
from app.services import domain_compounds
from app.services.audit_exports import record_export
from app.services.project_access import load_project_membership, require_project_role

_FEATURE_FLAG = Depends(require_feature_flag("AIDD_PROJECT_WORKSPACE_ENABLED"))

project_router = APIRouter(dependencies=[_FEATURE_FLAG])
router = APIRouter(dependencies=[_FEATURE_FLAG])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _download_url(file_id: str, user: User, *, expires_in: int = 3600) -> str:
    token = create_browser_file_access_token(
        file_id=file_id, user_id=str(user.id), expires_in_seconds=expires_in
    )
    return f"/api/v1/files/{file_id}/download?token={quote(token)}"


async def _load_project(db: AsyncSession, project_id: str) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise NotFoundException("研究项目不存在")
    return project


async def _read_import_file(
    db: AsyncSession, *, file_id: str, user: User, project_id: str
) -> tuple[FileModel, bytes]:
    record = await db.get(FileModel, file_id)
    if record is None or not is_file_usable(record) or not user_can_access_file(record, user):
        raise NotFoundException("文件不存在")
    if record.project_id and record.project_id != project_id:
        raise ValidationException("文件不属于当前项目")
    limit_mb = int(getattr(settings, "COMPOUND_IMPORT_MAX_FILE_SIZE_MB", 200) or 200)
    if record.size_bytes and int(record.size_bytes) > limit_mb * 1024 * 1024:
        raise ValidationException(f"文件超过 {limit_mb}MB 的分子库导入上限")
    return record, await read_file_bytes(record)


# ---------------------------------------------------------------------------
# Project-scoped collections
# ---------------------------------------------------------------------------


@project_router.get("/{project_id}/compounds", response_model=dict)
async def list_project_compounds(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = Query(None, max_length=DEFAULT_KEYWORD_MAX_LENGTH),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """化合物的项目视图：只列本项目候选物引用到的分子（docs/06 P-12 数据资产 Tab）。"""
    await load_project_membership(db, project_id=project_id, user_id=current_user.id)

    referenced = select(Candidate.compound_id).where(
        Candidate.project_id == project_id, Candidate.compound_id.is_not(None)
    )
    conditions = [Compound.id.in_(referenced)]
    if keyword:
        pattern = like_pattern(keyword)
        conditions.append(
            Compound.name.ilike(pattern, escape=LIKE_ESCAPE)
            | Compound.canonical_smiles.ilike(pattern, escape=LIKE_ESCAPE)
            | Compound.inchikey.ilike(pattern, escape=LIKE_ESCAPE)
        )

    total = await db.scalar(select(func.count(Compound.id)).where(*conditions))
    result = await db.execute(
        select(Compound)
        .where(*conditions)
        .order_by(Compound.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [domain_compounds.serialize_compound(item) for item in result.scalars().all()]
    return paginated_response(
        items=items, total=int(total or 0), page=page, page_size=page_size
    )


@project_router.post("/{project_id}/compounds", response_model=dict)
async def create_project_compound(
    project_id: str,
    data: CompoundCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """新增单个化合物。同 InChIKey 已存在时复用既有记录（M1-BR-1 去重）。"""
    await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles=domain_compounds.WRITE_ROLES,
    )
    compound, created = await domain_compounds.upsert_compound(
        db, smiles=data.smiles, name=data.name, user=current_user
    )
    await db.commit()
    return success_response(
        data=domain_compounds.serialize_compound(compound),
        message="化合物已创建" if created else "化合物已存在，已复用既有记录",
    )


@project_router.post("/{project_id}/compounds:import", response_model=dict)
async def import_project_compounds(
    project_id: str,
    data: CompoundImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量导入分子库（docs/05 §4.1 的同步版本）。

    与文档的差异：docs/05 把导入设计成异步任务（返回 ``taskId``），本实现做成
    同步接口。理由是一期导入量受 ``MAX_IMPORT_ROWS``（5 万行）约束，RDKit 解析
    一万条约 20 秒，仍在请求可接受范围内；改成任务需要新增 ``DATA_IMPORT`` 执行器
    与进度上报，属二期。**返回体保留 ``summary``/``errors`` 结构**，将来换成异步
    只需把 ``summary`` 挪到任务结果里，前端字段不变。
    """
    await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles=domain_compounds.WRITE_ROLES,
    )
    project = await _load_project(db, project_id)
    record, content = await _read_import_file(
        db, file_id=data.file_id, user=current_user, project_id=project_id
    )
    outcome = await domain_compounds.import_compounds(
        db,
        project=project,
        user=current_user,
        content=content,
        filename=record.filename or "",
        smiles_column=data.smiles_column,
        name_column=data.name_column,
        dedupe_strategy=data.dedupe_strategy,
        on_error=data.on_error,
    )
    await db.commit()
    return success_response(
        data={
            "summary": outcome.summary(),
            "errors": outcome.errors,
            "file_id": record.id,
        },
        message=f"导入完成：成功 {outcome.success} 条，失败 {outcome.failed} 条",
    )


@project_router.get("/{project_id}/candidates", response_model=dict)
async def list_project_candidates(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    candidate_type: str | None = Query(None, max_length=32),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await load_project_membership(db, project_id=project_id, user_id=current_user.id)
    conditions = [Candidate.project_id == project_id]
    if candidate_type:
        conditions.append(Candidate.candidate_type == candidate_type)

    total = await db.scalar(select(func.count(Candidate.id)).where(*conditions))
    result = await db.execute(
        select(Candidate)
        .where(*conditions)
        .order_by(Candidate.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    candidates = list(result.scalars().all())

    compound_ids = [item.compound_id for item in candidates if item.compound_id]
    compounds: dict[str, Compound] = {}
    if compound_ids:
        compound_result = await db.execute(
            select(Compound).where(Compound.id.in_(compound_ids))
        )
        compounds = {item.id: item for item in compound_result.scalars().all()}

    items = [
        domain_compounds.serialize_candidate(
            item, compound=compounds.get(item.compound_id) if item.compound_id else None
        )
        for item in candidates
    ]
    return paginated_response(
        items=items, total=int(total or 0), page=page, page_size=page_size
    )


@project_router.post("/{project_id}/candidates", response_model=dict)
async def create_project_candidate(
    project_id: str,
    data: CandidateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles=domain_compounds.WRITE_ROLES,
    )
    project = await _load_project(db, project_id)
    candidate = await domain_compounds.create_candidate(
        db,
        project=project,
        user=current_user,
        candidate_type=data.candidate_type,
        smiles=data.smiles,
        peptide_sequence=data.peptide_sequence,
        name=data.name,
        code=data.code,
        source=data.source,
        design_score=data.design_score,
        task_id=data.task_id,
        attrs=data.attrs,
    )
    await db.commit()
    compound = (
        await db.get(Compound, candidate.compound_id) if candidate.compound_id else None
    )
    return success_response(
        data=domain_compounds.serialize_candidate(candidate, compound=compound),
        message="候选物已创建",
    )


@project_router.get("/{project_id}/candidate-sets", response_model=dict)
async def list_project_candidate_sets(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    include_archived: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await load_project_membership(db, project_id=project_id, user_id=current_user.id)
    conditions = [CandidateSet.project_id == project_id]
    if not include_archived:
        conditions.append(CandidateSet.is_archived.is_(False))

    total = await db.scalar(select(func.count(CandidateSet.id)).where(*conditions))
    result = await db.execute(
        select(CandidateSet)
        .where(*conditions)
        .order_by(CandidateSet.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        domain_compounds.serialize_candidate_set(item) for item in result.scalars().all()
    ]
    return paginated_response(
        items=items, total=int(total or 0), page=page, page_size=page_size
    )


@project_router.post("/{project_id}/candidate-sets", response_model=dict)
async def create_project_candidate_set(
    project_id: str,
    data: CandidateSetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles=domain_compounds.WRITE_ROLES,
    )
    candidate_set = CandidateSet(
        project_id=project_id,
        created_by=current_user.id,
        name=data.name,
        description=data.description,
        source_task_id=data.source_task_id,
        item_count=0,
        version=1,
    )
    db.add(candidate_set)
    await db.commit()
    return success_response(
        data=domain_compounds.serialize_candidate_set(candidate_set),
        message="候选集已创建",
    )


# ---------------------------------------------------------------------------
# Compounds
# ---------------------------------------------------------------------------


@router.get("/compounds/{compound_id}", response_model=dict)
async def get_compound(
    compound_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """化合物详情。化合物是全局主数据，因此按「是否被当前用户可见项目引用」鉴权。"""
    compound = await domain_compounds.require_compound_read_access(
        db, compound_id=compound_id, user=current_user
    )
    return success_response(data=domain_compounds.serialize_compound(compound))


@router.post("/compounds:search", response_model=dict)
async def search_compounds_by_similarity(
    data: CompoundCreate,
    limit: int = Query(20, ge=1, le=200),
    threshold: float = Query(0.0, ge=0.0, le=1.0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按 ECFP4 Tanimoto 检索相似分子（docs/04 §5.7 一期实现）。

    只返回当前用户可见的化合物（其所属项目的候选物引用到的分子）；管理员返回全量。
    """
    hits = await domain_compounds.search_similar(
        db, smiles=data.smiles, user=current_user, limit=limit, threshold=threshold
    )
    return success_response(
        data={
            "query": {"smiles": data.smiles},
            "fingerprint": {"algorithm": "ECFP4", "bits": 2048},
            "items": [
                {
                    "compound": domain_compounds.serialize_compound(hit.compound),
                    "similarity": hit.similarity,
                }
                for hit in hits
            ],
        }
    )


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


@router.get("/candidates/{candidate_id}", response_model=dict)
async def get_candidate(
    candidate_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    candidate, compound = await domain_compounds.load_candidate_with_compound(db, candidate_id)
    await domain_compounds.require_candidate_read_access(
        db, candidate=candidate, user=current_user
    )
    return success_response(
        data=domain_compounds.serialize_candidate(candidate, compound=compound)
    )


@router.put("/candidates/{candidate_id}", response_model=dict)
async def update_candidate(
    candidate_id: str,
    data: CandidateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    candidate, compound = await domain_compounds.load_candidate_with_compound(db, candidate_id)
    await domain_compounds.require_candidate_write_access(
        db, candidate=candidate, user=current_user
    )
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(candidate, field, value)
    await db.commit()
    await db.refresh(candidate)
    return success_response(
        data=domain_compounds.serialize_candidate(candidate, compound=compound),
        message="候选物已更新",
    )


@router.post("/candidates:compare", response_model=dict)
async def compare_candidates(
    data: CandidateCompareRequest,
    project_id: str = Query(..., min_length=1, max_length=36),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """候选物并排比较（M3-FR-08，≤6 个）。``project_id`` 用于权限与归属校验。"""
    await load_project_membership(db, project_id=project_id, user_id=current_user.id)
    rows = await domain_compounds.compare_candidates(
        db, project_id=project_id, candidate_ids=data.candidate_ids
    )
    return success_response(data={"items": rows, "count": len(rows)})


@router.post("/candidates/{candidate_id}/fingerprint", response_model=dict)
async def compute_candidate_fingerprint(
    candidate_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """计算并缓存分子指纹（docs/04 §5.7）。多肽没有 2D 结构，返回 422。"""
    candidate, compound = await domain_compounds.load_candidate_with_compound(db, candidate_id)
    await domain_compounds.require_candidate_write_access(
        db, candidate=candidate, user=current_user
    )
    if candidate.candidate_type != CANDIDATE_TYPE_SMALL_MOLECULE or compound is None:
        raise ValidationException("只有小分子候选物支持分子指纹")
    fingerprint = await domain_compounds.ensure_fingerprint(db, compound)
    await db.commit()
    return success_response(
        data={
            "compound_id": compound.id,
            "ecfp4_bits": fingerprint.fp_ecfp4_bits,
            "ecfp4_bytes": len(fingerprint.fp_ecfp4 or b""),
            "maccs_bytes": len(fingerprint.fp_maccs or b""),
            "rdkit_version": fingerprint.rdkit_version,
        },
        message="分子指纹已计算",
    )


# ---------------------------------------------------------------------------
# Candidate sets
# ---------------------------------------------------------------------------


@router.get("/candidate-sets/{set_id}", response_model=dict)
async def get_candidate_set(
    set_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    candidate_set = await domain_compounds.load_candidate_set(db, set_id)
    await domain_compounds.require_set_read_access(
        db, candidate_set=candidate_set, user=current_user
    )
    return success_response(data=domain_compounds.serialize_candidate_set(candidate_set))


@router.put("/candidate-sets/{set_id}", response_model=dict)
async def update_candidate_set(
    set_id: str,
    data: CandidateSetUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新候选集（乐观锁，docs/04 §5.6）。版本不匹配返回 409 并带 ``currentVersion``。"""
    candidate_set = await domain_compounds.load_candidate_set(db, set_id)
    await domain_compounds.require_set_write_access(
        db, candidate_set=candidate_set, user=current_user
    )
    expected = data.expected_version if data.expected_version is not None else data.version
    updated = await domain_compounds.update_candidate_set(
        db,
        candidate_set=candidate_set,
        expected_version=int(expected),
        name=data.name,
        description=data.description,
    )
    await db.commit()
    return success_response(
        data=domain_compounds.serialize_candidate_set(updated), message="候选集已更新"
    )


@router.delete("/candidate-sets/{set_id}", response_model=dict)
async def delete_candidate_set(
    set_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """归档候选集（软删除）。集合项保留，便于历史结果仍能追溯到当时的集合。"""
    candidate_set = await domain_compounds.load_candidate_set(db, set_id)
    await domain_compounds.require_set_write_access(
        db, candidate_set=candidate_set, user=current_user
    )
    candidate_set.is_archived = True
    candidate_set.version = int(candidate_set.version or 1) + 1
    await db.commit()
    return success_response(
        data=domain_compounds.serialize_candidate_set(candidate_set), message="候选集已归档"
    )


@router.post("/candidate-sets/{set_id}/items", response_model=dict)
async def add_candidate_set_items(
    set_id: str,
    data: CandidateSetItemsAdd,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    candidate_set = await domain_compounds.load_candidate_set(db, set_id)
    await domain_compounds.require_set_write_access(
        db, candidate_set=candidate_set, user=current_user
    )
    inserted, skipped = await domain_compounds.add_set_items(
        db,
        candidate_set=candidate_set,
        candidate_ids=data.candidate_ids,
        snapshot_score=data.snapshot_score,
    )
    await db.commit()
    return success_response(
        data={
            "inserted": len(inserted),
            "skipped": skipped,
            "candidate_set": domain_compounds.serialize_candidate_set(candidate_set),
        },
        message=f"已加入 {len(inserted)} 个候选物，跳过 {skipped} 个",
    )


@router.get("/candidate-sets/{set_id}/items", response_model=dict)
async def list_candidate_set_items(
    set_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    candidate_set = await domain_compounds.load_candidate_set(db, set_id)
    await domain_compounds.require_set_read_access(
        db, candidate_set=candidate_set, user=current_user
    )
    total = await db.scalar(
        select(func.count(CandidateSetItem.id)).where(CandidateSetItem.set_id == set_id)
    )
    result = await db.execute(
        select(CandidateSetItem)
        .where(CandidateSetItem.set_id == set_id)
        .order_by(CandidateSetItem.ordinal.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(result.scalars().all())

    candidate_ids = [item.candidate_id for item in items]
    candidates: dict[str, Candidate] = {}
    compounds: dict[str, Compound] = {}
    if candidate_ids:
        candidate_result = await db.execute(
            select(Candidate).where(Candidate.id.in_(candidate_ids))
        )
        candidates = {item.id: item for item in candidate_result.scalars().all()}
        compound_ids = [item.compound_id for item in candidates.values() if item.compound_id]
        if compound_ids:
            compound_result = await db.execute(
                select(Compound).where(Compound.id.in_(compound_ids))
            )
            compounds = {item.id: item for item in compound_result.scalars().all()}

    payload = []
    for item in items:
        candidate = candidates.get(item.candidate_id)
        compound = (
            compounds.get(candidate.compound_id)
            if candidate is not None and candidate.compound_id
            else None
        )
        row = domain_compounds.serialize_set_item(item, candidate)
        if candidate is not None and compound is not None:
            row["candidate"] = domain_compounds.serialize_candidate(
                candidate, compound=compound
            )
        payload.append(row)

    return paginated_response(
        items=payload, total=int(total or 0), page=page, page_size=page_size
    )


@router.delete("/candidate-sets/{set_id}/items/{item_id}", response_model=dict)
async def remove_candidate_set_item(
    set_id: str,
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    candidate_set = await domain_compounds.load_candidate_set(db, set_id)
    await domain_compounds.require_set_write_access(
        db, candidate_set=candidate_set, user=current_user
    )
    item = await db.get(CandidateSetItem, item_id)
    if item is None or item.set_id != set_id:
        raise NotFoundException("候选集项不存在")
    await db.delete(item)
    candidate_set.item_count = max(0, int(candidate_set.item_count or 0) - 1)
    candidate_set.version = int(candidate_set.version or 1) + 1
    await db.commit()
    return success_response(
        data={
            "candidate_set": domain_compounds.serialize_candidate_set(candidate_set),
        },
        message="候选集项已移除",
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@router.post("/candidate-sets/{set_id}:export", response_model=dict)
async def export_candidate_set(
    set_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出候选集为 CSV（M3-FR-08「可导出」）。

    返回 CSV 文本而不是写文件：一期没有对象存储直传链路，前端拿到内容自行下载
    即可；将来接入 Artifact 版本管理时再改为写 ``artifacts`` 并返回 URN。
    """
    candidate_set = await domain_compounds.load_candidate_set(db, set_id)
    await domain_compounds.require_set_read_access(
        db, candidate_set=candidate_set, user=current_user
    )

    result = await db.execute(
        select(CandidateSetItem, Candidate)
        .join(Candidate, Candidate.id == CandidateSetItem.candidate_id)
        .where(CandidateSetItem.set_id == set_id)
        .order_by(CandidateSetItem.ordinal.asc())
    )
    rows = result.all()
    compound_ids = [candidate.compound_id for _, candidate in rows if candidate.compound_id]
    compounds: dict[str, Compound] = {}
    if compound_ids:
        compound_result = await db.execute(
            select(Compound).where(Compound.id.in_(compound_ids))
        )
        compounds = {item.id: item for item in compound_result.scalars().all()}

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "ordinal",
            "candidate_id",
            "candidate_type",
            "name",
            "code",
            "inchikey",
            "canonical_smiles",
            "mol_formula",
            "mol_weight",
            "logP",
            "QED",
            "design_score",
            "snapshot_score",
            "peptide_sequence",
            "SMILES",
        ]
    )
    for item, candidate in rows:
        compound = compounds.get(candidate.compound_id) if candidate.compound_id else None
        props = (compound.props or {}) if compound is not None else {}
        writer.writerow(
            [
                item.ordinal,
                candidate.id,
                candidate.candidate_type,
                candidate.name or "",
                candidate.code or "",
                compound.inchikey if compound else "",
                compound.canonical_smiles if compound else "",
                compound.mol_formula if compound else "",
                compound.mol_weight if compound else "",
                props.get("logP", ""),
                props.get("QED", ""),
                candidate.design_score if candidate.design_score is not None else "",
                item.snapshot_score if item.snapshot_score is not None else "",
                candidate.peptide_sequence or "",
                compound.canonical_smiles if compound else "",
            ]
        )

    content = buffer.getvalue()
    file_id = None
    try:
        from app.files.writer import store_file_bytes
        from app.models.files import FileSourceType

        stored = await store_file_bytes(
            db,
            content=content.encode("utf-8"),
            filename=f"{candidate_set.name or 'candidate-set'}.csv",
            content_type="text/csv",
            source_type=FileSourceType.TOOL_OUTPUT.value,
            owner_id=str(current_user.id),
            project_id=str(candidate_set.project_id),
            is_permanent=True,
        )
        await db.commit()
        file_id = stored.id
    except Exception:
        # 落盘失败不该让导出失败：直接把内容返回给前端下载。
        await db.rollback()
        file_id = None

    record_export(
        request=request,
        current_user=current_user,
        resource_type=ResourceType.CANDIDATE_SET,
        resource_id=str(candidate_set.id),
        resource_name=candidate_set.name,
        kind="candidate_set_csv",
        format="csv",
        row_count=len(rows),
        file_id=str(file_id) if file_id else None,
    )

    return success_response(
        data={
            "candidate_set_id": candidate_set.id,
            "row_count": len(rows),
            "file_id": file_id,
            "download_url": _download_url(file_id, current_user) if file_id else None,
            "content": None if file_id else content,
            "format": "csv",
        },
        message=f"已导出 {len(rows)} 行",
    )

__all__ = ["project_router", "router"]
