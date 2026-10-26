"""Target / protein / structure / pocket APIs (docs/05 §5, docs/01 M2).

端点分两组注册：

- ``project_router``（前缀 ``/projects``）：项目空间内的靶点集合
- ``router``（无前缀）：靶点、蛋白、结构、口袋的单项操作

领域逻辑集中在 ``app.services.domain_targets``，本模块只负责 HTTP 语义、
权限入口与响应包装。
"""

from __future__ import annotations

import hashlib
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.common.exceptions import NotFoundException, ValidationException
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.feature_flags import require_feature_flag
from app.files.content import read_file_bytes
from app.files.remote_access_tokens import create_browser_file_access_token
from app.files.writer import store_file_bytes
from app.models.files import File as FileModel, FileSourceType
from app.models.targets import PROTEIN_SOURCE_IMPORT, Protein, ProteinStructure, Target
from app.models.users import User
from app.models.versions import (
    ENTITY_TYPE_PROTEIN,
    SOURCE_TYPE_IMPORT,
    SOURCE_TYPE_MANUAL,
)
from app.schemas.targets import (
    PocketCreate,
    PocketSelectRequest,
    ProteinCreate,
    ProteinUpdate,
    StructureImport,
    StructurePredict,
    StructurePrepareRequest,
    TargetCreate,
    TargetUpdate,
)
from app.services import data_versions, domain_targets
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


def _structure_file_entry(
    label: str, urn: str | None, user: User
) -> dict | None:
    file_id = domain_targets.urn_file_id(urn)
    if file_id is None:
        return None
    return {
        "role": label,
        "file_id": file_id,
        "urn": urn,
        "download_url": _download_url(file_id, user),
    }


def _extract_fasta_sequence(raw: bytes, fallback_name: str) -> tuple[str, str]:
    """Return ``(sequence, name)`` from FASTA or plain-text content."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationException("序列文件必须是 UTF-8 文本（FASTA 或纯序列）") from exc
    header = ""
    chunks: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            if not header:
                header = stripped[1:].strip()
            continue
        chunks.append(stripped)
    sequence = "".join(chunks).upper()
    if not sequence:
        raise ValidationException("序列文件内容为空")
    if not all(ch.isalpha() or ch in "*-." for ch in sequence):
        raise ValidationException("序列包含非法字符，仅支持氨基酸字母与 * - . 占位符")
    name = header.split("|")[0].strip() if header else fallback_name
    return sequence, name or fallback_name


async def _read_accessible_file(
    db: AsyncSession, *, file_id: str, user: User, project_id: str
) -> FileModel:
    record = await db.get(FileModel, file_id)
    if record is None:
        raise NotFoundException("文件不存在")
    from app.files.file_records import is_file_usable, user_can_access_file

    if not is_file_usable(record) or not user_can_access_file(record, user):
        raise NotFoundException("文件不存在")
    if record.project_id and record.project_id != project_id:
        raise ValidationException("文件不属于当前项目")
    return record


def _structure_sha256_or_none(structure: ProteinStructure) -> str | None:
    return structure.sha256


def _protein_version_content(protein: Protein) -> dict:
    """版本指纹的取样范围：``sequence`` 与它归属的 ``target_id``。

    ``name`` 不进快照——给蛋白改名不改变它在结构预测里的任何输入，算成新版本
    会让「第几版」表示的其实是「保存过几次」。``seq_length`` 也不进：它是
    ``sequence`` 的派生量，重复计入只会让哈希对同一个序列算出两个值。
    """
    return {"target_id": protein.target_id, "sequence": protein.sequence}


# ---------------------------------------------------------------------------
# Project-scoped: targets
# ---------------------------------------------------------------------------


@project_router.get("/{project_id}/targets", response_model=dict)
async def list_project_targets(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = Query(None, max_length=128),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await load_project_membership(db, project_id=project_id, user_id=current_user.id)
    conditions = [Target.project_id == project_id]
    if keyword:
        conditions.append(Target.name.ilike(f"%{keyword}%"))
    total = await db.scalar(select(func.count(Target.id)).where(*conditions))
    result = await db.execute(
        select(Target)
        .options(selectinload(Target.proteins))
        .where(*conditions)
        .order_by(Target.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        domain_targets.serialize_target(item, include_proteins=False)
        for item in result.scalars().all()
    ]
    return paginated_response(
        items=items, total=int(total or 0), page=page, page_size=page_size
    )


@project_router.post("/{project_id}/targets", response_model=dict)
async def create_project_target(
    project_id: str,
    data: TargetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_role(
        db, project_id=project_id, user=current_user, allowed_roles=domain_targets.WRITE_ROLES
    )
    duplicated = await db.execute(
        select(Target.id).where(
            Target.project_id == project_id, Target.name == data.name
        )
    )
    if duplicated.scalar_one_or_none() is not None:
        raise ValidationException("同一项目下已存在同名靶点", detail={"name": data.name})
    target = Target(
        project_id=project_id,
        created_by=current_user.id,
        **data.model_dump(),
    )
    db.add(target)
    await db.commit()
    target = await domain_targets.load_target(db, target.id)
    return success_response(
        data=domain_targets.serialize_target(target, include_proteins=False),
        message="靶点已创建",
    )


@project_router.get("/{project_id}/targets/{target_id}", response_model=dict)
async def get_project_target(
    project_id: str,
    target_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await load_project_membership(db, project_id=project_id, user_id=current_user.id)
    target = await domain_targets.load_target(db, target_id)
    if target.project_id != project_id:
        raise NotFoundException("靶点不存在")
    return success_response(data=domain_targets.serialize_target(target))


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


@router.get("/targets/{target_id}", response_model=dict)
async def get_target(
    target_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target = await domain_targets.load_target(db, target_id)
    await domain_targets.require_target_read_access(db, target=target, user=current_user)
    return success_response(data=domain_targets.serialize_target(target))


@router.put("/targets/{target_id}", response_model=dict)
async def update_target(
    target_id: str,
    data: TargetUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target = await domain_targets.load_target(db, target_id)
    await domain_targets.require_target_write_access(
        db, target=target, user=current_user
    )
    payload = data.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"] != target.name:
        duplicated = await db.execute(
            select(Target.id).where(
                Target.project_id == target.project_id,
                Target.name == payload["name"],
                Target.id != target.id,
            )
        )
        if duplicated.scalar_one_or_none() is not None:
            raise ValidationException(
                "同一项目下已存在同名靶点", detail={"name": payload["name"]}
            )
    for field_name, value in payload.items():
        setattr(target, field_name, value)
    await db.commit()
    target = await domain_targets.load_target(db, target.id)
    return success_response(
        data=domain_targets.serialize_target(target), message="靶点已更新"
    )


@router.delete("/targets/{target_id}", response_model=dict)
async def delete_target(
    target_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target = await domain_targets.load_target(db, target_id)
    await domain_targets.require_target_write_access(
        db, target=target, user=current_user
    )
    project_id = str(target.project_id)
    await domain_targets.delete_target_cascade(db, target_id=target_id)
    return success_response(
        data={"id": target_id, "project_id": project_id}, message="靶点已删除"
    )


# ---------------------------------------------------------------------------
# Proteins
# ---------------------------------------------------------------------------


@router.post("/targets/{target_id}/proteins", response_model=dict)
async def create_protein(
    target_id: str,
    data: ProteinCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target = await domain_targets.load_target(db, target_id)
    await domain_targets.require_target_write_access(
        db, target=target, user=current_user
    )

    sequence = (data.sequence or "").strip()
    name = data.name
    if not sequence:
        assert data.file_id is not None  # schema 已保证二选一
        record = await _read_accessible_file(
            db, file_id=data.file_id, user=current_user, project_id=str(target.project_id)
        )
        content = await read_file_bytes(record)
        sequence, parsed_name = _extract_fasta_sequence(content, name)
        if not data.name.strip():
            name = parsed_name
    normalized = "".join(sequence.split()).upper()
    if not normalized:
        raise ValidationException("蛋白序列不能为空")

    protein = Protein(
        target_id=target_id,
        name=name,
        sequence=normalized,
        seq_length=len(normalized),
        source=data.source,
        current_version=1,
    )
    db.add(protein)
    await db.flush()
    # 版本行必须落在 commit 之前：否则蛋白写入失败会留下一条指向不存在蛋白的
    # 孤儿版本；而 ``record_version`` 自己不 commit（见 data_versions 模块说明）。
    await data_versions.record_version(
        db,
        entity_type=ENTITY_TYPE_PROTEIN,
        entity_id=str(protein.id),
        source_type=(
            SOURCE_TYPE_IMPORT if data.source == PROTEIN_SOURCE_IMPORT else SOURCE_TYPE_MANUAL
        ),
        user=current_user,
        change_summary="新建蛋白序列（第 1 版）",
        content=_protein_version_content(protein),
    )
    await db.commit()
    protein = await domain_targets.load_protein(db, protein.id)
    return success_response(
        data=domain_targets.serialize_protein(protein), message="蛋白已创建"
    )


@router.get("/proteins/{protein_id}", response_model=dict)
async def get_protein(
    protein_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    protein = await domain_targets.load_protein(db, protein_id)
    target = await domain_targets.protein_target(db, protein)
    await domain_targets.require_target_read_access(db, target=target, user=current_user)
    return success_response(data=domain_targets.serialize_protein(protein))


@router.put("/proteins/{protein_id}", response_model=dict)
async def update_protein(
    protein_id: str,
    data: ProteinUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    protein = await domain_targets.load_protein(db, protein_id)
    target = await domain_targets.protein_target(db, protein)
    await domain_targets.require_target_write_access(
        db, target=target, user=current_user
    )
    payload = data.model_dump(exclude_unset=True)
    if "sequence" in payload and payload["sequence"] is not None:
        normalized = "".join(str(payload["sequence"]).split()).upper()
        if not normalized:
            raise ValidationException("蛋白序列不能为空")
        # 只有序列**真的变了**才递增版本号并记版：否则用户连续点两次保存、什么都没改，
        # 版本号也会跳两格，``current_version`` 就不再表示「序列被改过几次」。判据是
        # 内容哈希（与 compounds 的复用分支同一口径），比的是「与上一版」而不是「与
        # 历史任意版」——改回原序列仍然算一次真实改动，版本照常递增。
        before_hash = data_versions.content_hash_of(_protein_version_content(protein))
        protein.sequence = normalized
        protein.seq_length = len(normalized)
        content = _protein_version_content(protein)
        if data_versions.content_hash_of(content) != before_hash:
            protein.current_version = (protein.current_version or 1) + 1
            # 与 create_protein 同理：版本行落在 commit 之前，且 record_version 自己不
            # commit。若哪一步失败，``current_version`` 的递增与版本行会一起回滚，
            # 不会出现「计数器跳了、历史没记」的自相矛盾。
            await data_versions.record_version(
                db,
                entity_type=ENTITY_TYPE_PROTEIN,
                entity_id=str(protein.id),
                source_type=SOURCE_TYPE_MANUAL,
                user=current_user,
                change_summary=f"更新蛋白序列（第 {protein.current_version} 版）",
                content=content,
            )
    if "name" in payload and payload["name"] is not None:
        protein.name = payload["name"]
    await db.commit()
    protein = await domain_targets.load_protein(db, protein.id)
    return success_response(
        data=domain_targets.serialize_protein(protein), message="蛋白已更新"
    )


@router.post("/proteins/{protein_id}/structures:predict", response_model=dict)
async def predict_structure(
    protein_id: str,
    data: StructurePredict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    protein = await domain_targets.load_protein(db, protein_id)
    if not protein.sequence:
        raise ValidationException("蛋白缺少序列，无法提交结构预测")
    task = await domain_targets.submit_structure_prediction(
        db, protein=protein, user=current_user, data=data
    )
    position = await domain_targets.task_queue_position(db, task=task)
    return success_response(
        data=domain_targets.serialize_task_submission(task, queue_position=position),
        message="结构预测任务已提交",
    )


@router.post("/proteins/{protein_id}/structures:import", response_model=dict)
async def import_structure(
    protein_id: str,
    data: StructureImport,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    protein = await domain_targets.load_protein(db, protein_id)
    target = await domain_targets.protein_target(db, protein)
    await domain_targets.require_target_write_access(
        db, target=target, user=current_user
    )
    project_id = str(target.project_id)

    source = await _read_accessible_file(
        db, file_id=data.file_id, user=current_user, project_id=project_id
    )
    content = await read_file_bytes(source)
    if not content:
        raise ValidationException("结构文件内容为空")

    stored = await store_file_bytes(
        db,
        content=content,
        filename=data.name or source.filename,
        content_type=source.content_type or "chemical/x-pdb",
        source_type=FileSourceType.USER_INPUT,
        owner_id=current_user.id,
        project_id=project_id,
        file_meta={"imported_from": source.id, "role": "protein_structure"},
    )
    plddt_file_id: str | None = None
    if data.plddt_file_id:
        plddt_source = await _read_accessible_file(
            db, file_id=data.plddt_file_id, user=current_user, project_id=project_id
        )
        plddt_stored = await store_file_bytes(
            db,
            content=await read_file_bytes(plddt_source),
            filename=plddt_source.filename,
            content_type=plddt_source.content_type or "application/json",
            source_type=FileSourceType.USER_INPUT,
            owner_id=current_user.id,
            project_id=project_id,
            file_meta={"imported_from": plddt_source.id, "role": "plddt"},
        )
        plddt_file_id = str(plddt_stored.id)

    structure = ProteinStructure(
        protein_id=protein_id,
        source_type=data.source_type,
        structure_urn=domain_targets.file_urn(stored.id),
        sha256=hashlib.sha256(content).hexdigest(),
        plddt_urn=domain_targets.file_urn(plddt_file_id) if plddt_file_id else None,
        model_name=data.model_name,
        model_version=data.model_version,
    )
    db.add(structure)
    await db.commit()
    structure = await domain_targets.load_structure(db, structure.id)
    return success_response(
        data=domain_targets.serialize_structure(structure), message="结构已导入"
    )


@router.get("/proteins/{protein_id}/structures", response_model=dict)
async def list_protein_structures(
    protein_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    protein = await domain_targets.load_protein(db, protein_id)
    target = await domain_targets.protein_target(db, protein)
    await domain_targets.require_target_read_access(db, target=target, user=current_user)
    structures = sorted(
        domain_targets.loaded_relationship(protein, "structures") or [],
        key=lambda item: item.created_at,
        reverse=True,
    )
    return success_response(
        data={
            "items": [
                domain_targets.serialize_structure(item) for item in structures
            ]
        }
    )


# ---------------------------------------------------------------------------
# Structures
# ---------------------------------------------------------------------------


@router.get("/structures/{structure_id}", response_model=dict)
async def get_structure(
    structure_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    structure = await domain_targets.load_structure(db, structure_id)
    target = await domain_targets.structure_target(db, structure)
    await domain_targets.require_target_read_access(db, target=target, user=current_user)
    return success_response(
        data=domain_targets.serialize_structure(structure, include_pockets=True)
    )


@router.post("/structures/{structure_id}:prepare", response_model=dict)
async def prepare_structure(
    structure_id: str,
    data: StructurePrepareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    structure = await domain_targets.load_structure(db, structure_id)
    task = await domain_targets.submit_structure_preparation(
        db, structure=structure, user=current_user, data=data
    )
    position = await domain_targets.task_queue_position(db, task=task)
    return success_response(
        data=domain_targets.serialize_task_submission(task, queue_position=position),
        message="结构准备任务已提交",
    )


@router.get("/structures/{structure_id}/pdb", response_model=dict)
async def get_structure_pdb(
    structure_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回结构的下载地址（docs/05 §5 结构文件接口统一返回预签名 URL）。"""
    structure = await domain_targets.load_structure(db, structure_id)
    target = await domain_targets.structure_target(db, structure)
    await domain_targets.require_target_read_access(db, target=target, user=current_user)
    entries = [
        entry
        for entry in (
            _structure_file_entry("structure", structure.structure_urn, current_user),
            _structure_file_entry("prepared", structure.prepared_urn, current_user),
            _structure_file_entry("pdbqt", structure.pdbqt_urn, current_user),
        )
        if entry is not None
    ]
    if not entries:
        raise NotFoundException("该结构尚无可用文件")
    return success_response(
        data={
            "structure_id": structure.id,
            "sha256": _structure_sha256_or_none(structure),
            "files": entries,
        }
    )


@router.post("/structures/{structure_id}:export", response_model=dict)
async def export_structure(
    structure_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出结构包：返回全部角色文件的下载地址清单（离线内网无外链）。"""
    structure = await domain_targets.load_structure(db, structure_id)
    target = await domain_targets.structure_target(db, structure)
    await domain_targets.require_target_read_access(db, target=target, user=current_user)
    files = [
        entry
        for entry in (
            _structure_file_entry("structure", structure.structure_urn, current_user),
            _structure_file_entry("prepared", structure.prepared_urn, current_user),
            _structure_file_entry("pdbqt", structure.pdbqt_urn, current_user),
            _structure_file_entry("plddt", structure.plddt_urn, current_user),
        )
        if entry is not None
    ]
    if not files:
        raise NotFoundException("该结构尚无可用文件")
    return success_response(
        data={
            "structure_id": structure.id,
            "protein_id": structure.protein_id,
            "source_type": structure.source_type,
            "sha256": structure.sha256,
            "model": {
                "name": structure.model_name,
                "version": structure.model_version,
            },
            "files": files,
        },
        message="结构导出清单已生成",
    )


# ---------------------------------------------------------------------------
# Pockets
# ---------------------------------------------------------------------------


@router.get("/structures/{structure_id}/pockets", response_model=dict)
async def list_structure_pockets(
    structure_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    structure = await domain_targets.load_structure(db, structure_id)
    target = await domain_targets.structure_target(db, structure)
    await domain_targets.require_target_read_access(db, target=target, user=current_user)
    pockets = sorted(
        domain_targets.loaded_relationship(structure, "pockets") or [],
        key=lambda item: (item.rank or 0, item.created_at),
    )
    return success_response(
        data={"items": [domain_targets.serialize_pocket(item) for item in pockets]}
    )


@router.post("/structures/{structure_id}/pockets", response_model=dict)
async def create_structure_pocket(
    structure_id: str,
    data: PocketCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    structure = await domain_targets.load_structure(db, structure_id)
    target = await domain_targets.structure_target(db, structure)
    await domain_targets.require_target_write_access(
        db, target=target, user=current_user
    )
    pocket = await domain_targets.create_pocket(db, structure=structure, data=data)
    return success_response(
        data=domain_targets.serialize_pocket(pocket, include_residues=True),
        message="口袋已登记",
    )


@router.post("/structures/{structure_id}/pockets:predict", response_model=dict)
async def predict_structure_pockets(
    structure_id: str,
    data: StructurePredict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    structure = await domain_targets.load_structure(db, structure_id)
    task = await domain_targets.submit_pocket_prediction(
        db, structure=structure, user=current_user, data=data
    )
    position = await domain_targets.task_queue_position(db, task=task)
    return success_response(
        data=domain_targets.serialize_task_submission(task, queue_position=position),
        message="口袋预测任务已提交",
    )


@router.get("/pockets/{pocket_id}", response_model=dict)
async def get_pocket(
    pocket_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pocket = await domain_targets.load_pocket(db, pocket_id)
    structure = await domain_targets.pocket_structure(db, pocket)
    target = await domain_targets.structure_target(db, structure)
    await domain_targets.require_target_read_access(db, target=target, user=current_user)
    return success_response(
        data=domain_targets.serialize_pocket(pocket, include_residues=True)
    )


@router.post("/pockets/{pocket_id}:select", response_model=dict)
async def select_pocket(
    pocket_id: str,
    data: PocketSelectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pocket = await domain_targets.load_pocket(db, pocket_id)
    structure = await domain_targets.pocket_structure(db, pocket)
    target = await domain_targets.structure_target(db, structure)
    await domain_targets.require_target_write_access(
        db, target=target, user=current_user
    )
    updated = await domain_targets.select_pocket(
        db, pocket=pocket, selected=data.selected
    )
    return success_response(
        data=domain_targets.serialize_pocket(updated),
        message="口袋已选定" if data.selected else "口袋已取消选定",
    )


@router.get("/pockets/{pocket_id}/residues", response_model=dict)
async def list_pocket_residues(
    pocket_id: str,
    key_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pocket = await domain_targets.load_pocket(db, pocket_id)
    structure = await domain_targets.pocket_structure(db, pocket)
    target = await domain_targets.structure_target(db, structure)
    await domain_targets.require_target_read_access(db, target=target, user=current_user)
    residues = list(domain_targets.loaded_relationship(pocket, "residues") or [])
    if key_only:
        residues = [item for item in residues if item.is_key]
    residues.sort(key=lambda item: (item.chain, item.residue_seq))
    return success_response(
        data={
            "pocket_id": pocket.id,
            "structure_id": pocket.structure_id,
            "items": [domain_targets.serialize_residue(item) for item in residues],
        }
    )


__all__ = [
    "project_router",
    "router",
]
