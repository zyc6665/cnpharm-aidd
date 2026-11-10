"""把任务结果回写领域表（docs/26 H-16）。

为什么需要这一层
----------------
计算的终点原本停在 ``ArtifactVersion``：产物、哈希、血缘都齐了，但「这个结构属于
哪个蛋白」「这个口袋属于哪个结构」只存在于提交参数里。于是 Boltz-2 结构预测跑完
``protein_structures`` 没有新行、结构准备跑完 ``prepared_urn`` 仍是空、LVpocket 跑完
``pockets`` 没有新行——页面只能显示手工导入和种子数据，``GuidedWorkflow`` 的
「结构预测完成」判定也永远拿不到新结构（docs/26 H-16）。

设计口径
--------
- **只认标准产物契约**，不读工具私有 metrics：``protein_structure@1`` →
  ``protein_structures``，``binding_pocket@1`` → ``pockets`` + ``pocket_residues``。
  换一个同样声明了标准产物的模型，回写不需要改代码。
- **按任务幂等**：同一 ``task_id`` 重放（重试、远端补回）只更新不新增，口袋是
  先删本任务旧行再写，避免 ``uq_pockets_structure_rank`` 冲突与重复行。
- **失败不降级任务状态**：回写失败只回一个 ``status="failed"`` 的标记并记日志。
  计算结果已经付出算力，不该因为落库问题被判成失败；标记会随任务详情暴露，
  免得像 H-16 那样静默几个月。
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.execution.result_parser import ParsedStandardArtifact
from app.files.content import read_file_bytes
from app.models.files import File as FileModel
from app.models.targets import (
    STRUCTURE_SOURCE_PREDICTED,
    Pocket,
    PocketResidue,
    Protein,
    ProteinStructure,
)
from app.models.tasks import Task
from app.services.domain_targets import file_urn
from app.services.standard_artifacts import StandardArtifactPersistenceResult

logger = logging.getLogger(__name__)

DOMAIN_WRITEBACK_KEY = "domain_writeback"

STRUCTURE_STANDARD_TYPE = "protein_structure@1"
POCKET_STANDARD_TYPE = "binding_pocket@1"

#: 结构产物的文件角色：boltz2 用 ``structure_file``，结构准备用 ``prepared_pdb``。
STRUCTURE_FILE_ROLES = ("structure_file", "prepared_pdb")
PDBQT_FILE_ROLE = "receptor_pdbqt"
POCKET_RESIDUE_FILE_ROLE = "residue_pocket_pdb"

STATUS_WRITTEN = "written"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"


def domain_context(task: Task) -> dict[str, Any] | None:
    """返回提交时写入的领域上下文（``extra_data["domain"]``）。"""
    extra_data = task.extra_data if isinstance(task.extra_data, dict) else {}
    domain = extra_data.get("domain")
    return domain if isinstance(domain, dict) else None


def domain_kind(task: Task) -> str | None:
    domain = domain_context(task)
    kind = domain.get("kind") if domain else None
    return str(kind) if kind else None


async def write_back_domain_results(
    db: AsyncSession,
    *,
    task: Task,
    persistence_result: StandardArtifactPersistenceResult | None,
    tool: Any | None = None,
    tool_version: Any | None = None,
) -> dict[str, Any] | None:
    """任务成功后把标准产物投影到领域表；无领域上下文时返回 ``None``。"""
    kind = domain_kind(task)
    if kind is None:
        return None

    marker: dict[str, Any] = {"kind": kind, "taskId": str(task.id)}
    try:
        # 用 SAVEPOINT 圈住回写：失败只回滚这一段，不能把同一事务里已经写好的
        # 产物、TaskOutput 一起回滚掉——那等于让领域数据的问题毁掉计算结果。
        async with db.begin_nested():
            if persistence_result is None:
                marker.update(status=STATUS_SKIPPED, reason="任务没有标准产物，无法投影领域数据")
            elif kind == "structure_prediction":
                marker.update(
                    await _write_structure_prediction(
                        db, task=task, persistence_result=persistence_result,
                        tool=tool, tool_version=tool_version,
                    )
                )
            elif kind == "structure_preparation":
                marker.update(
                    await _write_structure_preparation(
                        db, task=task, persistence_result=persistence_result,
                        tool=tool, tool_version=tool_version,
                    )
                )
            elif kind == "pocket_prediction":
                marker.update(
                    await _write_pocket_prediction(
                        db, task=task, persistence_result=persistence_result,
                        tool=tool, tool_version=tool_version,
                    )
                )
            else:
                marker.update(status=STATUS_SKIPPED, reason=f"未支持的领域类型: {kind}")
    except Exception as exc:  # noqa: BLE001 - 领域回写失败不能连带任务失败
        logger.exception("任务 %s 领域回写失败（%s）", task.id, kind)
        marker.update(status=STATUS_FAILED, reason=str(exc))

    _stamp_marker(task, marker)
    return marker


def _stamp_marker(task: Task, marker: dict[str, Any]) -> None:
    extra_data = dict(task.extra_data) if isinstance(task.extra_data, dict) else {}
    extra_data[DOMAIN_WRITEBACK_KEY] = marker
    task.extra_data = extra_data


# ---------------------------------------------------------------------------
# 结构预测
# ---------------------------------------------------------------------------


async def _write_structure_prediction(
    db: AsyncSession,
    *,
    task: Task,
    persistence_result: StandardArtifactPersistenceResult,
    tool: Any | None,
    tool_version: Any | None,
) -> dict[str, Any]:
    domain = domain_context(task) or {}
    protein_id = _text(domain.get("protein_id"))
    if protein_id is None:
        return {"status": STATUS_SKIPPED, "reason": "任务缺少 protein_id"}
    protein = await db.get(Protein, protein_id)
    if protein is None:
        return {"status": STATUS_SKIPPED, "reason": f"蛋白已不存在: {protein_id}"}

    located = _first_structure_artifact(persistence_result)
    if located is None:
        return {"status": STATUS_SKIPPED, "reason": f"没有 {STRUCTURE_STANDARD_TYPE} 产物"}
    ref, artifact, file_id = located

    file_record = await db.get(FileModel, file_id)
    if file_record is None:
        return {"status": STATUS_SKIPPED, "reason": f"结构文件记录已不存在: {file_id}"}

    model_ref = domain.get("model_ref") if isinstance(domain.get("model_ref"), dict) else {}
    structure = await _structure_for_task(db, protein_id=protein_id, task_id=str(task.id))
    if structure is None:
        structure = ProteinStructure(protein_id=protein_id, task_id=str(task.id))
        db.add(structure)

    structure.source_type = STRUCTURE_SOURCE_PREDICTED
    structure.structure_urn = file_urn(file_id)
    structure.sha256 = file_record.sha256 or _artifact_sha256(artifact)
    structure.plddt_mean = _plddt_mean(artifact.metrics)
    structure.model_name = _text(model_ref.get("name")) or _tool_name(tool)
    structure.model_version = _text(model_ref.get("version")) or _tool_version_name(tool_version)
    structure.tool_name = _tool_name(tool)
    structure.tool_version = _tool_version_name(tool_version)
    await db.flush()

    return {
        "status": STATUS_WRITTEN,
        "structureId": str(structure.id),
        "proteinId": protein_id,
        "artifactRef": ref,
        "plddtMean": None if structure.plddt_mean is None else float(structure.plddt_mean),
    }


# ---------------------------------------------------------------------------
# 结构准备
# ---------------------------------------------------------------------------


async def _write_structure_preparation(
    db: AsyncSession,
    *,
    task: Task,
    persistence_result: StandardArtifactPersistenceResult,
    tool: Any | None,
    tool_version: Any | None,
) -> dict[str, Any]:
    domain = domain_context(task) or {}
    structure_id = _text(domain.get("structure_id"))
    if structure_id is None:
        return {"status": STATUS_SKIPPED, "reason": "任务缺少 structure_id"}
    structure = await db.get(ProteinStructure, structure_id)
    if structure is None:
        return {"status": STATUS_SKIPPED, "reason": f"结构已不存在: {structure_id}"}

    located = _first_structure_artifact(persistence_result)
    if located is None:
        return {"status": STATUS_SKIPPED, "reason": f"没有 {STRUCTURE_STANDARD_TYPE} 产物"}
    ref, _artifact, prepared_file_id = located

    # 结构准备不新建结构行：它把「可对接版本」挂回原始结构（docs/04 §6.3 的
    # prepared_urn / pdbqt_urn），下游口袋预测与对接按 role 取。
    structure.prepared_urn = file_urn(prepared_file_id)
    pdbqt_file_id = _role_file_id(persistence_result, ref, PDBQT_FILE_ROLE)
    if pdbqt_file_id is not None:
        structure.pdbqt_urn = file_urn(pdbqt_file_id)
    if structure.tool_name is None:
        structure.tool_name = _tool_name(tool)
    if structure.tool_version is None:
        structure.tool_version = _tool_version_name(tool_version)
    await db.flush()

    return {
        "status": STATUS_WRITTEN,
        "structureId": str(structure.id),
        "preparedUrn": structure.prepared_urn,
        "pdbqtUrn": structure.pdbqt_urn,
    }


# ---------------------------------------------------------------------------
# 口袋预测
# ---------------------------------------------------------------------------


async def _write_pocket_prediction(
    db: AsyncSession,
    *,
    task: Task,
    persistence_result: StandardArtifactPersistenceResult,
    tool: Any | None,
    tool_version: Any | None,
) -> dict[str, Any]:
    domain = domain_context(task) or {}
    structure_id = _text(domain.get("structure_id"))
    if structure_id is None:
        return {"status": STATUS_SKIPPED, "reason": "任务缺少 structure_id"}
    structure = await db.get(ProteinStructure, structure_id)
    if structure is None:
        return {"status": STATUS_SKIPPED, "reason": f"结构已不存在: {structure_id}"}

    pockets = list(_artifacts_of_type(persistence_result, POCKET_STANDARD_TYPE))
    if not pockets:
        return {"status": STATUS_SKIPPED, "reason": f"没有 {POCKET_STANDARD_TYPE} 产物"}

    task_id = str(task.id)
    removed = await _delete_task_pockets(db, structure_id=structure_id, task_id=task_id)
    # rank 在结构内唯一（uq_pockets_structure_rank）：新一轮预测接在已有最大值之后，
    # 不能从 1 重排，否则同结构的第二次预测必然撞唯一约束。
    base_rank = await db.scalar(
        select(func.max(Pocket.rank)).where(Pocket.structure_id == structure_id)
    )
    next_rank = int(base_rank or 0) + 1

    created: list[str] = []
    residue_total = 0
    for ref, artifact in pockets:
        residues = await _pocket_residues(db, persistence_result, ref)
        geometry = _pocket_geometry(artifact)
        residue_ids = _sequence(artifact.metadata.get("residue_ids"))
        pocket = Pocket(
            structure_id=structure_id,
            rank=next_rank,
            score=_number(artifact.metadata.get("score")),
            volume=geometry["volume"],
            center_x=geometry["center"][0],
            center_y=geometry["center"][1],
            center_z=geometry["center"][2],
            box_size_x=geometry["box_size"][0],
            box_size_y=geometry["box_size"][1],
            box_size_z=geometry["box_size"][2],
            residue_count=len(residues) or len(residue_ids) or None,
            selected=False,
            tool_name=_tool_name(tool),
            tool_version=_tool_version_name(tool_version),
            task_id=task_id,
        )
        db.add(pocket)
        await db.flush()
        for residue in residues:
            db.add(
                PocketResidue(
                    pocket_id=pocket.id,
                    chain=residue["chain"],
                    residue_seq=residue["residue_seq"],
                    residue_name=residue["residue_name"],
                    # 残基清单本身就是模型给出的「口袋残基」集合，逐条标为关键残基；
                    # 逐残基贡献度模型没有输出，留空而不是编一个数。
                    is_key=True,
                    contribution=None,
                )
            )
        await db.flush()
        created.append(str(pocket.id))
        residue_total += len(residues)
        next_rank += 1

    return {
        "status": STATUS_WRITTEN,
        "structureId": structure_id,
        "pocketIds": created,
        "residueCount": residue_total,
        "replacedPockets": removed,
    }


async def _delete_task_pockets(
    db: AsyncSession, *, structure_id: str, task_id: str
) -> int:
    """删除本任务上次写入的口袋（重放幂等），子行显式删以免异步会话懒加载。"""
    pocket_ids = list(
        (
            await db.execute(
                select(Pocket.id).where(
                    Pocket.structure_id == structure_id, Pocket.task_id == task_id
                )
            )
        )
        .scalars()
        .all()
    )
    if not pocket_ids:
        return 0
    await db.execute(delete(PocketResidue).where(PocketResidue.pocket_id.in_(pocket_ids)))
    await db.execute(delete(Pocket).where(Pocket.id.in_(pocket_ids)))
    await db.flush()
    return len(pocket_ids)


async def _pocket_residues(
    db: AsyncSession,
    persistence_result: StandardArtifactPersistenceResult,
    ref: str,
) -> list[dict[str, Any]]:
    file_id = _role_file_id(persistence_result, ref, POCKET_RESIDUE_FILE_ROLE)
    if file_id is None:
        return []
    file_record = await db.get(FileModel, file_id)
    if file_record is None:
        return []
    try:
        content = await read_file_bytes(file_record)
    except FileNotFoundError:
        logger.warning("口袋残基文件读不到: %s", file_id)
        return []
    return parse_pdb_residues(content)


def parse_pdb_residues(content: bytes) -> list[dict[str, Any]]:
    """从 PDB 文本抽取去重后的残基三元组（chain, resSeq, resName）。

    ``pocket_residues.residue_name`` 是 NOT NULL，所以残基名只能从结构文件里读，
    不能编。PDB 固定列位：17-20 残基名、21 链、22-26 残基序号。
    """
    seen: set[tuple[str, int, str]] = set()
    residues: list[dict[str, Any]] = []
    for raw_line in content.decode("utf-8", errors="ignore").splitlines():
        if not raw_line.startswith(("ATOM", "HETATM")):
            continue
        if len(raw_line) < 27:
            continue
        name = raw_line[17:20].strip()
        chain = raw_line[21].strip() or "A"
        seq_text = raw_line[22:26].strip()
        if not name or not seq_text.isdigit():
            continue
        key = (chain, int(seq_text), name)
        if key in seen:
            continue
        seen.add(key)
        residues.append({"chain": chain, "residue_seq": int(seq_text), "residue_name": name})
    return residues


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------


def _artifacts_of_type(
    persistence_result: StandardArtifactPersistenceResult, standard_type: str
) -> Iterable[tuple[str, ParsedStandardArtifact]]:
    for ref, artifact in persistence_result.parsed_artifacts_by_ref.items():
        if artifact.type == standard_type:
            yield ref, artifact


def _first_structure_artifact(
    persistence_result: StandardArtifactPersistenceResult,
) -> tuple[str, ParsedStandardArtifact, str] | None:
    """取第一个带结构文件的 ``protein_structure@1`` 产物（含 ref、产物、文件 id）。"""
    for ref, artifact in _artifacts_of_type(persistence_result, STRUCTURE_STANDARD_TYPE):
        for role in STRUCTURE_FILE_ROLES:
            file_id = _role_file_id(persistence_result, ref, role)
            if file_id is not None:
                return ref, artifact, file_id
    return None


def _role_file_id(
    persistence_result: StandardArtifactPersistenceResult, ref: str, role: str
) -> str | None:
    roles = persistence_result.file_ids_by_artifact_role.get(ref) or {}
    return _text(roles.get(role))


def _artifact_sha256(artifact: ParsedStandardArtifact) -> str | None:
    for parsed_file in artifact.files.values():
        if parsed_file.sha256:
            return parsed_file.sha256
    return None


def _plddt_mean(metrics: dict[str, Any]) -> float | None:
    """pLDDT 均值统一成 0~100；模型给 0~1 的概率值就地换算。"""
    for key in ("plddt_mean", "mean_plddt", "complex_plddt", "plddt", "confidence_score"):
        value = _number(metrics.get(key))
        if value is None:
            continue
        if 0.0 <= value <= 1.0:
            value *= 100.0
        if value < 0.0 or value > 100.0:
            continue
        return round(value, 2)
    return None


def _pocket_geometry(artifact: ParsedStandardArtifact) -> dict[str, Any]:
    """从产物 metadata 取口袋几何；缺 bbox 时中心与体积留空，不编造。

    ``binding_pocket@1`` 的规范 metadata 只有 ``center`` / ``bbox`` /
    ``residue_ids``，没有 ``score`` 与 ``volume``——体积只能由 bbox 三边相乘得到，
    因此几何缺失时对应列就是 NULL，而不是 0（0 会被当成真实体积参与排序）。
    """
    center = _vector3(artifact.metadata.get("center")) or _vector3(
        artifact.metadata.get("centroid")
    )
    bbox = artifact.metadata.get("bbox") if isinstance(artifact.metadata.get("bbox"), dict) else {}
    min_corner = _vector3(bbox.get("min")) if bbox else None
    max_corner = _vector3(bbox.get("max")) if bbox else None
    box_size: list[float | None] = [None, None, None]
    if min_corner is not None and max_corner is not None:
        box_size = [round(abs(hi - lo), 3) for lo, hi in zip(min_corner, max_corner)]
    volume = None
    dims = [item for item in box_size if item is not None]
    if len(dims) == 3:
        volume = round(dims[0] * dims[1] * dims[2], 3)
    return {
        "center": center or [None, None, None],
        "box_size": box_size,
        "volume": volume,
    }


def _vector3(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    numbers = [_number(item) for item in value]
    if any(item is None for item in numbers):
        return None
    return [round(float(item), 3) for item in numbers if item is not None]


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _tool_name(tool: Any | None) -> str | None:
    if tool is None:
        return None
    return _text(getattr(tool, "slug", None)) or _text(getattr(tool, "name", None))


def _tool_version_name(tool_version: Any | None) -> str | None:
    if tool_version is None:
        return None
    return _text(getattr(tool_version, "version", None))


async def _structure_for_task(
    db: AsyncSession, *, protein_id: str, task_id: str
) -> ProteinStructure | None:
    result = await db.execute(
        select(ProteinStructure).where(
            ProteinStructure.protein_id == protein_id,
            ProteinStructure.task_id == task_id,
        )
    )
    return result.scalars().first()
