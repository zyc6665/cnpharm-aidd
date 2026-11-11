"""Shared domain logic for targets, proteins, structures and pockets (docs/04 §6).

本模块提供 M2 靶点结构分析所需的领域用例，供 API 层与后续任务回写复用：

- 实体装载与 404 语义（``load_*``）
- 响应序列化（``serialize_*``），字段口径与 docs/05 §5 一致
- 结构文件内容解析（``structure_file_records``）
- 口袋选定的事务性切换（``select_pocket``）
- 结构预测 / 结构准备 / 口袋预测的任务提交（``submit_*``）

设计口径：
- 领域表只存 URN 与 sha256，文件内容始终走 ``files`` 表，避免第二份真值源
  （docs/04 §1「元数据入库、文件入对象存储」）。
- 任务提交统一走 ``create_and_schedule_tool_task``，与单项任务、工作流节点同一
  执行单元（docs/01 M6-BR-1），领域层不自行排队。
- ``model_ref`` 优先于默认工具列表：后续落地模型注册时不需要改本模块。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import ConflictException, NotFoundException, ValidationException
from app.common.task_status import task_status_to_api
from app.common.time import isoformat_utc
from app.files.file_records import is_file_usable, user_can_access_file
from app.models.artifacts import ArtifactVersionFile
from app.models.files import File as FileModel
from app.models.targets import Pocket, PocketResidue, Protein, ProteinStructure, Target
from app.models.tasks import Task, TaskStatus
from app.models.tools import Tool, ToolStatus
from app.models.users import User
from app.schemas.tasks import TaskCreate
from app.schemas.targets import PocketCreate, StructurePredict, StructurePrepareRequest
from app.services.pocket_residue_scoring import tier_for
from app.services.project_access import load_project_membership, require_project_role
from app.services.standard_input_slots import tool_accepts_standard_input_bindings
from app.tasks.service import create_and_schedule_tool_task

WRITE_ROLES = ("owner", "editor")
READ_ROLES = ("owner", "editor", "runner", "viewer")

#: 结构预测默认工具候选（按顺序取第一个已发布工具）。
#: ``boltz-2`` 对应 docs/07 §1.1 已定型模型；工具记录在模型注册步骤落地。
STRUCTURE_PREDICT_TOOL_SLUGS: tuple[str, ...] = (
    "boltz-2",
    "boltz2-structure-prediction",
)
#: 口袋预测默认工具候选（``20260821_01`` 迁移已注册 lvpocket）。
POCKET_PREDICT_TOOL_SLUGS: tuple[str, ...] = ("lvpocket-pocket-prediction",)
#: 结构准备默认工具候选（``20260930_01`` 迁移已注册内置工具）。
STRUCTURE_PREPARE_TOOL_SLUGS: tuple[str, ...] = ("builtin-protein-preparation",)

FILE_URN_PREFIX = "file:"


# ---------------------------------------------------------------------------
# URN helpers
# ---------------------------------------------------------------------------


def file_urn(file_id: str) -> str:
    """Return the canonical URN for a platform file (docs/04 §1: 库内只存 urn + sha256)."""
    return f"{FILE_URN_PREFIX}{file_id}"


def urn_file_id(urn: str | None) -> str | None:
    """Extract the file id from a ``file:`` URN; unknown schemes return ``None``."""
    if not urn or not urn.startswith(FILE_URN_PREFIX):
        return None
    value = urn[len(FILE_URN_PREFIX) :].strip()
    return value or None


# ---------------------------------------------------------------------------
# Loading & access
# ---------------------------------------------------------------------------


async def load_target(db: AsyncSession, target_id: str) -> Target:
    result = await db.execute(
        select(Target)
        .options(selectinload(Target.proteins).selectinload(Protein.structures))
        .where(Target.id == target_id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise NotFoundException("靶点不存在")
    return target


async def load_protein(db: AsyncSession, protein_id: str) -> Protein:
    result = await db.execute(
        select(Protein)
        .options(selectinload(Protein.structures).selectinload(ProteinStructure.pockets))
        .where(Protein.id == protein_id)
    )
    protein = result.scalar_one_or_none()
    if protein is None:
        raise NotFoundException("蛋白不存在")
    return protein


async def load_structure(db: AsyncSession, structure_id: str) -> ProteinStructure:
    result = await db.execute(
        select(ProteinStructure)
        .options(selectinload(ProteinStructure.pockets))
        .where(ProteinStructure.id == structure_id)
    )
    structure = result.scalar_one_or_none()
    if structure is None:
        raise NotFoundException("蛋白结构不存在")
    return structure


async def load_pocket(db: AsyncSession, pocket_id: str) -> Pocket:
    result = await db.execute(
        select(Pocket).options(selectinload(Pocket.residues)).where(Pocket.id == pocket_id)
    )
    pocket = result.scalar_one_or_none()
    if pocket is None:
        raise NotFoundException("口袋不存在")
    return pocket


async def require_target_write_access(db: AsyncSession, *, target: Target, user: User) -> None:
    await require_project_role(
        db,
        project_id=str(target.project_id),
        user=user,
        allowed_roles=WRITE_ROLES,
    )


async def require_target_read_access(db: AsyncSession, *, target: Target, user: User) -> None:
    await load_project_membership(
        db, project_id=str(target.project_id), user_id=str(user.id)
    )


async def protein_target(db: AsyncSession, protein: Protein) -> Target:
    return await load_target(db, str(protein.target_id))


async def structure_protein(db: AsyncSession, structure: ProteinStructure) -> Protein:
    return await load_protein(db, str(structure.protein_id))


async def structure_target(db: AsyncSession, structure: ProteinStructure) -> Target:
    return await protein_target(db, await structure_protein(db, structure))


async def pocket_structure(db: AsyncSession, pocket: Pocket) -> ProteinStructure:
    return await load_structure(db, str(pocket.structure_id))


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _iso(value: Any) -> Any:
    """序列化时间时补 ``Z``，避免前端按本地时区解释 naive UTC。

    见 ``app.common.time.isoformat_utc``：库里存的是 naive UTC，裸 ``isoformat()``
    会让东八区用户看到的时间整体晚 8 小时。
    """
    if hasattr(value, "isoformat"):
        return isoformat_utc(value)
    return value


def loaded_relationship(obj: Any, attr: str) -> Any:
    """Return an already-loaded relationship value without triggering lazy IO.

    异步会话下访问未加载的关系会抛 ``MissingGreenlet``；序列化只消费调用方
    用 ``selectinload`` 提前装载好的数据（docs/04 §5.6 并发控制约定）。
    """
    return obj.__dict__.get(attr)


def _number(value: Any) -> Any:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def serialize_residue(residue: PocketResidue) -> dict:
    contribution = _number(residue.contribution)
    return {
        "id": residue.id,
        "pocket_id": residue.pocket_id,
        "chain": residue.chain,
        "residue_seq": residue.residue_seq,
        "residue_name": residue.residue_name,
        "is_key": bool(residue.is_key),
        "contribution": contribution,
        # 分级由分数派生而不是另存一列：阈值调整后历史数据自动跟着变口径，
        # 不会出现「分数 0.72 但标签写着外围」这种自相矛盾的行。
        "score_tier": tier_for(contribution) if contribution is not None else None,
    }


def serialize_pocket(pocket: Pocket, *, include_residues: bool = False) -> dict:
    data = {
        "id": pocket.id,
        "structure_id": pocket.structure_id,
        "rank": pocket.rank,
        "score": _number(pocket.score),
        "volume": _number(pocket.volume),
        "center": {
            "x": _number(pocket.center_x),
            "y": _number(pocket.center_y),
            "z": _number(pocket.center_z),
        },
        "box_size": {
            "x": _number(pocket.box_size_x),
            "y": _number(pocket.box_size_y),
            "z": _number(pocket.box_size_z),
        },
        "residue_count": pocket.residue_count,
        "selected": bool(pocket.selected),
        "tool": {"name": pocket.tool_name, "version": pocket.tool_version},
        "task_id": pocket.task_id,
        "created_at": _iso(pocket.created_at),
        "updated_at": _iso(pocket.updated_at),
    }
    if include_residues:
        data["residues"] = [serialize_residue(item) for item in (loaded_relationship(pocket, "residues") or [])]
    return data


def serialize_structure(structure: ProteinStructure, *, include_pockets: bool = False) -> dict:
    data = {
        "id": structure.id,
        "protein_id": structure.protein_id,
        "source_type": structure.source_type,
        "structure_urn": structure.structure_urn,
        "structure_file_id": urn_file_id(structure.structure_urn),
        "prepared_urn": structure.prepared_urn,
        "prepared_file_id": urn_file_id(structure.prepared_urn),
        "pdbqt_urn": structure.pdbqt_urn,
        "pdbqt_file_id": urn_file_id(structure.pdbqt_urn),
        "sha256": structure.sha256,
        "plddt_mean": _number(structure.plddt_mean),
        "plddt_urn": structure.plddt_urn,
        "plddt_file_id": urn_file_id(structure.plddt_urn),
        "model": {"name": structure.model_name, "version": structure.model_version},
        "tool": {"name": structure.tool_name, "version": structure.tool_version},
        "task_id": structure.task_id,
        "created_at": _iso(structure.created_at),
        "updated_at": _iso(structure.updated_at),
    }
    if include_pockets:
        data["pockets"] = [serialize_pocket(item) for item in (loaded_relationship(structure, "pockets") or [])]
    return data


def serialize_protein(protein: Protein, *, include_structures: bool = True) -> dict:
    data = {
        "id": protein.id,
        "target_id": protein.target_id,
        "name": protein.name,
        "sequence": protein.sequence,
        "seq_length": protein.seq_length,
        "source": protein.source,
        "current_version": protein.current_version,
        "created_at": _iso(protein.created_at),
        "updated_at": _iso(protein.updated_at),
    }
    if include_structures:
        data["structures"] = [
            serialize_structure(item) for item in (loaded_relationship(protein, "structures") or [])
        ]
    return data


def serialize_target(target: Target, *, include_proteins: bool = True) -> dict:
    data = {
        "id": target.id,
        "project_id": target.project_id,
        "created_by": target.created_by,
        "name": target.name,
        "target_type": target.target_type,
        "uniprot_id": target.uniprot_id,
        "gene_name": target.gene_name,
        "description": target.description,
        "created_at": _iso(target.created_at),
        "updated_at": _iso(target.updated_at),
    }
    if include_proteins:
        data["proteins"] = [
            serialize_protein(item, include_structures=False)
            for item in (loaded_relationship(target, "proteins") or [])
        ]
    return data


# ---------------------------------------------------------------------------
# Structure file access
# ---------------------------------------------------------------------------


def _structure_urn(structure: ProteinStructure, role: str) -> str | None:
    return {
        "structure": structure.structure_urn,
        "prepared": structure.prepared_urn,
        "pdbqt": structure.pdbqt_urn,
        "plddt": structure.plddt_urn,
    }.get(role, structure.structure_urn)


async def structure_file_records(
    db: AsyncSession,
    *,
    structure: ProteinStructure,
    user: User,
    role: str = "structure",
) -> FileModel:
    """Return the ``files`` row backing a structure role, enforcing readability."""
    file_id = urn_file_id(_structure_urn(structure, role))
    if file_id is None:
        raise NotFoundException(f"该结构没有 {role} 文件")
    record = await db.get(FileModel, file_id)
    if record is None or not is_file_usable(record) or not user_can_access_file(record, user):
        raise NotFoundException(f"该结构的 {role} 文件不存在或已过期")
    return record


async def structure_input_file_record(
    db: AsyncSession, *, structure: ProteinStructure, user: User
) -> FileModel:
    """下游计算（口袋预测/对接）的输入结构：有准备版本就优先用它。

    任务规格 TGT-04-1 要求口袋预测以「结构准备后的可对接结构」为输入。过去这里
    固定取 ``structure``（原始结构），准备产物等于白算；结构准备回写
    ``prepared_urn`` 之后按角色取值才闭环（docs/26 H-16）。
    """
    role = "prepared" if _structure_urn(structure, "prepared") else "structure"
    return await structure_file_records(db, structure=structure, user=user, role=role)


# ---------------------------------------------------------------------------
# Pocket selection & creation
# ---------------------------------------------------------------------------


async def select_pocket(db: AsyncSession, *, pocket: Pocket, selected: bool) -> Pocket:
    """Select/deselect a pocket, keeping at most one selected pocket per structure.

    选中前先把同结构下已选中的口袋置为未选中，避免触发
    ``uq_pockets_selected_structure`` 分区唯一索引（docs/04 §5.6）。
    """
    if selected:
        await db.execute(
            sa_update(Pocket)
            .where(
                Pocket.structure_id == pocket.structure_id,
                Pocket.id != pocket.id,
                Pocket.selected.is_(True),
            )
            .values(selected=False)
        )
    pocket.selected = selected
    await db.commit()
    return await load_pocket(db, pocket.id)


async def create_pocket(
    db: AsyncSession, *, structure: ProteinStructure, data: PocketCreate
) -> Pocket:
    """手工登记口袋（外部工具结果导入等）；预测产出的口袋由任务回写创建。"""
    existing = await db.execute(
        select(Pocket.id).where(
            Pocket.structure_id == structure.id, Pocket.rank == data.rank
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictException(
            f"该结构已存在 rank={data.rank} 的口袋", detail={"rank": data.rank}
        )

    pocket = Pocket(
        structure_id=structure.id,
        rank=data.rank,
        score=data.score,
        volume=data.volume,
        center_x=data.center_x,
        center_y=data.center_y,
        center_z=data.center_z,
        box_size_x=data.box_size_x,
        box_size_y=data.box_size_y,
        box_size_z=data.box_size_z,
        residue_count=len(data.residues) or None,
        selected=False,
        tool_name=data.tool_name,
        tool_version=data.tool_version,
    )
    db.add(pocket)
    await db.flush()

    for residue in data.residues:
        db.add(
            PocketResidue(
                pocket_id=pocket.id,
                chain=residue.chain,
                residue_seq=residue.residue_seq,
                residue_name=residue.residue_name,
                is_key=residue.is_key,
                contribution=residue.contribution,
            )
        )
    await db.commit()
    return await load_pocket(db, pocket.id)


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


async def delete_target_cascade(db: AsyncSession, *, target_id: str) -> None:
    """Delete a target with its proteins, structures, pockets and residues.

    显式按序删除而不是依赖 ORM cascade：异步会话下隐式懒加载会抛
    ``MissingGreenlet``，且数据库层没有 ``ON DELETE CASCADE``。
    """
    structure_ids = select(ProteinStructure.id).join(
        Protein, Protein.id == ProteinStructure.protein_id
    ).where(Protein.target_id == target_id)
    pocket_ids = select(Pocket.id).where(Pocket.structure_id.in_(structure_ids))
    await db.execute(sa_delete(PocketResidue).where(PocketResidue.pocket_id.in_(pocket_ids)))
    await db.execute(sa_delete(Pocket).where(Pocket.structure_id.in_(structure_ids)))
    await db.execute(
        sa_delete(ProteinStructure).where(
            ProteinStructure.protein_id.in_(
                select(Protein.id).where(Protein.target_id == target_id)
            )
        )
    )
    await db.execute(sa_delete(Protein).where(Protein.target_id == target_id))
    await db.execute(sa_delete(Target).where(Target.id == target_id))
    await db.commit()


async def delete_project_domain_rows(db: AsyncSession, *, project_id: str) -> None:
    """Delete every target-side row of a project before the project row goes away.

    项目删除是最终一致操作（docs/03 §3.2.2），但领域表没有 ``ON DELETE CASCADE``，
    因此必须在同一个事务里显式按序清理，否则 ``targets.project_id`` 外键会阻断删除。
    """
    structure_ids = (
        select(ProteinStructure.id)
        .join(Protein, Protein.id == ProteinStructure.protein_id)
        .join(Target, Target.id == Protein.target_id)
        .where(Target.project_id == project_id)
    )
    pocket_ids = select(Pocket.id).where(Pocket.structure_id.in_(structure_ids))
    await db.execute(
        sa_delete(PocketResidue).where(PocketResidue.pocket_id.in_(pocket_ids))
    )
    await db.execute(sa_delete(Pocket).where(Pocket.structure_id.in_(structure_ids)))
    await db.execute(sa_delete(ProteinStructure).where(ProteinStructure.id.in_(structure_ids)))
    await db.execute(
        sa_delete(Protein).where(
            Protein.target_id.in_(select(Target.id).where(Target.project_id == project_id))
        )
    )
    await db.execute(sa_delete(Target).where(Target.project_id == project_id))


# ---------------------------------------------------------------------------
# Task submission
# ---------------------------------------------------------------------------


async def resolve_tool(
    db: AsyncSession, *, slugs: Sequence[str], requested_slug: str | None
) -> Tool:
    candidates: Iterable[str] = (requested_slug,) if requested_slug else slugs
    for slug in candidates:
        if not slug:
            continue
        result = await db.execute(
            select(Tool)
            .options(selectinload(Tool.current_version))
            .where(Tool.slug == slug, Tool.status == ToolStatus.PUBLISHED.value)
        )
        tool = result.scalar_one_or_none()
        if tool is not None and tool.current_version is not None:
            return tool
    wanted = requested_slug or slugs[0]
    raise ConflictException(
        f"工具尚未注册或未发布：{wanted}",
        detail={"slug": wanted, "hint": "请先在模型与工具管理中注册该模型镜像（见 docs/07）"},
    )


async def submit_structure_prediction(
    db: AsyncSession, *, protein: Protein, user: User, data: StructurePredict
) -> Task:
    target = await protein_target(db, protein)
    await require_target_write_access(db, target=target, user=user)
    tool = await resolve_tool(
        db,
        slugs=STRUCTURE_PREDICT_TOOL_SLUGS,
        requested_slug=data.model_ref.name if data.model_ref else None,
    )
    params: dict[str, Any] = {
        "sequence": protein.sequence,
        "seq_length": protein.seq_length,
        **data.params,
    }
    return await create_and_schedule_tool_task(
        db=db,
        current_user=user,
        task_data=TaskCreate(
            name=f"结构预测 · {protein.name}",
            project_id=str(target.project_id),
            tool_id=str(tool.id),
            tool_version_id=str(tool.current_version_id) if tool.current_version_id else None,
            params=params,
            file_ids=[],
            priority=data.priority,
        ),
        extra_data={
            "domain": {
                "kind": "structure_prediction",
                "target_id": str(target.id),
                "protein_id": str(protein.id),
                "model_ref": data.model_ref.model_dump() if data.model_ref else None,
            }
        },
    )


async def submit_structure_preparation(
    db: AsyncSession, *, structure: ProteinStructure, user: User, data: StructurePrepareRequest
) -> Task:
    target = await structure_target(db, structure)
    await require_target_write_access(db, target=target, user=user)
    source = await structure_file_records(db, structure=structure, user=user)
    tool = await resolve_tool(
        db, slugs=STRUCTURE_PREPARE_TOOL_SLUGS, requested_slug=data.tool_slug
    )
    return await create_and_schedule_tool_task(
        db=db,
        current_user=user,
        task_data=TaskCreate(
            name=f"结构准备 · {structure.id[:8]}",
            project_id=str(target.project_id),
            tool_id=str(tool.id),
            tool_version_id=str(tool.current_version_id) if tool.current_version_id else None,
            params=dict(data.params),
            # 内置工具的输入不是「随便挂几个文件」：执行器按标准输入槽名取文件
            # （``builtin_inputs[protein_structure@1]``）。只给 ``file_ids`` 的话，
            # 任务能提交、能排队，但跑到执行器里必然报「缺少 protein_structure@1 输入」。
            standard_input_uploads={"protein": str(source.id)},
            priority=data.priority,
        ),
        extra_data={
            "domain": {
                "kind": "structure_preparation",
                "structure_id": str(structure.id),
            }
        },
    )

async def structure_task_input(
    db: AsyncSession, *, tool: Tool, file_id: str
) -> dict[str, Any]:
    """按工具形态给出任务的输入取值。

    两种工具对「输入」的要求不一样：
    - tool-package v2 工具（LVpocket / GROMACS）在 k8s 上执行时，输入必须是已经落盘
      的标准 ``ArtifactVersion``，给裸文件 id 会在执行前就报「Kubernetes 输入需要
      已落盘的标准 ArtifactVersion」；
    - 内置工具（结构准备）由执行器按标准输入槽名取文件，需要 ``standard_input_uploads``。

    所以先按 v2 口径找该文件的产物版本，找不到再退回标准输入上传。
    """
    config = getattr(getattr(tool, "current_version", None), "config", None) or {}
    if tool_accepts_standard_input_bindings(config):
        version_id = (
            await db.execute(
                select(ArtifactVersionFile.artifact_version_id)
                .where(ArtifactVersionFile.file_id == file_id)
                .order_by(ArtifactVersionFile.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if version_id:
            return {"input_bindings": {"protein": str(version_id)}}
    return {"standard_input_uploads": {"protein": file_id}}


async def submit_pocket_prediction(
    db: AsyncSession, *, structure: ProteinStructure, user: User, data: StructurePredict
) -> Task:
    target = await structure_target(db, structure)
    await require_target_write_access(db, target=target, user=user)
    source = await structure_input_file_record(db, structure=structure, user=user)
    tool = await resolve_tool(
        db,
        slugs=POCKET_PREDICT_TOOL_SLUGS,
        requested_slug=data.model_ref.name if data.model_ref else None,
    )
    params: dict[str, Any] = dict(data.params)
    if "top_k" in params:
        try:
            params["top_k"] = int(params["top_k"])
        except (TypeError, ValueError) as exc:
            raise ValidationException("top_k 必须是整数") from exc
    task_input = await structure_task_input(db, tool=tool, file_id=str(source.id))
    return await create_and_schedule_tool_task(
        db=db,
        current_user=user,
        task_data=TaskCreate(
            name=f"口袋预测 · {structure.id[:8]}",
            project_id=str(target.project_id),
            tool_id=str(tool.id),
            tool_version_id=str(tool.current_version_id) if tool.current_version_id else None,
            params=params,
            **task_input,
            priority=data.priority,
        ),
        extra_data={
            "domain": {
                "kind": "pocket_prediction",
                "structure_id": str(structure.id),
                "model_ref": data.model_ref.model_dump() if data.model_ref else None,
            }
        },
    )


# ---------------------------------------------------------------------------
# Counters & submission payloads
# ---------------------------------------------------------------------------


async def project_domain_counts(db: AsyncSession, *, project_id: str) -> dict[str, int]:
    """Target/structure/pocket counters for the project overview card (docs/06 P-04)."""
    targets = (
        await db.execute(
            select(func.count()).select_from(Target).where(Target.project_id == project_id)
        )
    ).scalar_one()
    structures = (
        await db.execute(
            select(func.count())
            .select_from(ProteinStructure)
            .join(Protein, Protein.id == ProteinStructure.protein_id)
            .join(Target, Target.id == Protein.target_id)
            .where(Target.project_id == project_id)
        )
    ).scalar_one()
    pockets = (
        await db.execute(
            select(func.count())
            .select_from(Pocket)
            .join(ProteinStructure, ProteinStructure.id == Pocket.structure_id)
            .join(Protein, Protein.id == ProteinStructure.protein_id)
            .join(Target, Target.id == Protein.target_id)
            .where(Target.project_id == project_id)
        )
    ).scalar_one()
    return {
        "targets": int(targets or 0),
        "structures": int(structures or 0),
        "pockets": int(pockets or 0),
    }


async def task_queue_position(db: AsyncSession, *, task: Task) -> int | None:
    """Best-effort queue position for the submission response (docs/05 §5.1).

    提交响应返回前，``dispatch_tool_task`` 已把任务从 PENDING 置为 QUEUED，
    所以判定与计数都必须同时认 PENDING 和 QUEUED；只认 ``"pending"`` 会让
    queue_position 恒为 None。库里存的是大写枚举值，比较也须用枚举值。
    位置按 ``priority`` + ``created_at`` 统计排在前面的任务数（1 起，含自己）。
    """
    waiting_statuses = (TaskStatus.PENDING.value, TaskStatus.QUEUED.value)
    if task.status not in waiting_statuses:
        return None
    position = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                Task.status.in_(waiting_statuses),
                Task.priority == task.priority,
                Task.created_at <= task.created_at,
            )
        )
    ).scalar_one()
    return int(position or 0) or None


def serialize_task_submission(task: Task, *, queue_position: int | None) -> dict:
    """任务提交回执（docs/05 §5.1）。

    ``status`` 与任务列表/结果接口同一套小写 API 契约：库里存的是大写枚举值，
    直接透出会让前端拿到 ``QUEUED`` 而按 ``queued`` 解析不到。走
    ``task_status_to_api`` 统一转换。
    """
    return {
        "task_id": task.id,
        "status": task_status_to_api(task.status),
        "queue_position": queue_position,
        "priority": task.priority,
    }


__all__ = [
    "FILE_URN_PREFIX",
    "POCKET_PREDICT_TOOL_SLUGS",
    "READ_ROLES",
    "STRUCTURE_PREDICT_TOOL_SLUGS",
    "STRUCTURE_PREPARE_TOOL_SLUGS",
    "WRITE_ROLES",
    "create_pocket",
    "delete_project_domain_rows",
    "delete_target_cascade",
    "file_urn",
    "load_pocket",
    "load_protein",
    "load_structure",
    "load_target",
    "loaded_relationship",
    "pocket_structure",
    "project_domain_counts",
    "protein_target",
    "require_target_read_access",
    "require_target_write_access",
    "resolve_tool",
    "select_pocket",
    "serialize_pocket",
    "serialize_protein",
    "serialize_residue",
    "serialize_structure",
    "serialize_target",
    "serialize_task_submission",
    "structure_file_records",
    "structure_protein",
    "structure_target",
    "submit_pocket_prediction",
    "submit_structure_prediction",
    "submit_structure_preparation",
    "task_queue_position",
    "urn_file_id",
]
