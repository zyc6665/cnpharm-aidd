"""研发阶段纯推导（docs/05 §3.2，docs/03 §3.6.1）。

**为什么不加 ``project.stage`` 字段**：阶段是数据的投影，不是数据本身。一旦落库，
用户新建靶点后就出现「库里写 S1、实际已经到 S2」的分歧，而唯一的修法是让每个写
路径都记得回填——那正是这类字段最终都变成脏数据的路径。这里每次 GET 现算，允许
回退（删掉最后一个靶点就退回 S0），不阻塞任何操作。

阶段是**导航与提示**，不是门禁：``gaps`` 列出当前阶段「还差什么」，调用方拿它渲染
下一步提示，但任何接口都不因 ``gaps`` 非空而拒绝写入。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compounds import Candidate
from app.models.decisions import DecisionRecord
from app.models.tasks import Task, TaskStatus
from app.models.targets import Pocket, Protein, ProteinStructure, Target


STAGE_NAMES = {
    "S0": "立项与数据归集",
    "S1": "靶点确立",
    "S2": "结构与口袋就绪",
    "S3": "候选生成",
    "S4": "性质评估",
    "S5": "计算验证",
}

#: 顺序即优先级：``gaps`` 先报挡住整条链路的那一条。最多给 5 条——再多就不是
#: 「下一步做什么」，而是一份让人不想读的待办清单。
GAP_ORDER = (
    "NO_TARGET",
    "NO_STRUCTURE",
    "NO_POCKET_SELECTED",
    "NO_CANDIDATE",
    "NO_TASK",
)

#: 一条任务到达这里才算「结果可看」；排队与运行中仍属于「已提交」。
FINISHED_STATUSES = (TaskStatus.SUCCESS.value,)
SUBMITTED_STATUSES = (TaskStatus.RUNNING.value, TaskStatus.SUCCESS.value)


async def _count(db: AsyncSession, statement) -> int:
    return int((await db.execute(statement)).scalar_one() or 0)


async def compute_project_stage(db: AsyncSession, *, project_id: str) -> dict:
    """Derive the project stage from its data; never writes.

    ``S0 项目已建`` → ``S1 靶点已建`` → ``S2 结构与口袋就绪`` → ``S3 候选物已生成``
    → ``S4 已提交计算`` → ``S5 已有结果``。
    """
    target_count = await _count(
        db, select(func.count()).select_from(Target).where(Target.project_id == project_id)
    )
    structure_count = await _count(
        db,
        select(func.count())
        .select_from(ProteinStructure)
        .join(Protein, Protein.id == ProteinStructure.protein_id)
        .join(Target, Target.id == Protein.target_id)
        .where(Target.project_id == project_id),
    )
    selected_pocket_count = await _count(
        db,
        select(func.count())
        .select_from(Pocket)
        .join(ProteinStructure, ProteinStructure.id == Pocket.structure_id)
        .join(Protein, Protein.id == ProteinStructure.protein_id)
        .join(Target, Target.id == Protein.target_id)
        .where(Target.project_id == project_id, Pocket.selected.is_(True)),
    )
    candidate_count = await _count(
        db,
        select(func.count()).select_from(Candidate).where(Candidate.project_id == project_id),
    )
    task_filter = Task.project_id_expression() == project_id
    submitted_task_count = await _count(
        db,
        select(func.count())
        .select_from(Task)
        .where(task_filter, Task.status.in_(SUBMITTED_STATUSES)),
    )
    finished_task_count = await _count(
        db,
        select(func.count())
        .select_from(Task)
        .where(task_filter, Task.status.in_(FINISHED_STATUSES)),
    )

    reached = ["S0"]
    if target_count > 0:
        reached.append("S1")
    if target_count > 0 and structure_count > 0 and selected_pocket_count > 0:
        reached.append("S2")
    if len(reached) == 3 and candidate_count > 0:
        reached.append("S3")
    if len(reached) == 4 and submitted_task_count > 0:
        reached.append("S4")
    if len(reached) == 5 and finished_task_count > 0:
        reached.append("S5")

    current_stage = reached[-1]
    next_stage = (
        f"S{int(current_stage[1:]) + 1}" if current_stage != "S5" else None
    )

    gaps: list[dict] = []
    if target_count == 0:
        gaps.append(
            {
                "code": "NO_TARGET",
                "message": "项目还没有靶点",
                "action": "前往靶点与结构页新建靶点",
            }
        )
    if target_count > 0 and structure_count == 0:
        gaps.append(
            {
                "code": "NO_STRUCTURE",
                "message": f"已有 {target_count} 个靶点，但还没有导入结构",
                "action": "在蛋白详情导入 PDB 结构或提交结构预测任务",
            }
        )
    if structure_count > 0 and selected_pocket_count == 0:
        gaps.append(
            {
                "code": "NO_POCKET_SELECTED",
                "message": f"已有 {structure_count} 个结构，但尚未选定口袋",
                "action": "前往结构详情选择口袋",
            }
        )
    if len(reached) >= 3 and candidate_count == 0:
        gaps.append(
            {
                "code": "NO_CANDIDATE",
                "message": "结构与口袋已就绪，但还没有候选物",
                "action": "提交候选生成任务，或手工录入候选物",
            }
        )
    if len(reached) >= 4 and submitted_task_count == 0:
        gaps.append(
            {
                "code": "NO_TASK",
                "message": "已有候选物，但还没有提交过计算任务",
                "action": "在候选物页选择候选并提交评估任务",
            }
        )

    decision_count = await _count(
        db,
        select(func.count())
        .select_from(DecisionRecord)
        .where(DecisionRecord.project_id == project_id),
    )

    ordered = sorted(
        gaps,
        key=lambda gap: (
            GAP_ORDER.index(gap["code"]) if gap["code"] in GAP_ORDER else len(GAP_ORDER)
        ),
    )
    return {
        "current_stage": current_stage,
        "stage_name": STAGE_NAMES[current_stage],
        "reached_stages": reached,
        "next_stage": next_stage,
        "gaps": ordered[:5],
        "counters": {
            "targets": target_count,
            "structures": structure_count,
            "selected_pockets": selected_pocket_count,
            "candidates": candidate_count,
            "submitted_tasks": submitted_task_count,
            "finished_tasks": finished_task_count,
            "decisions": decision_count,
        },
    }


__all__ = [
    "FINISHED_STATUSES",
    "GAP_ORDER",
    "STAGE_NAMES",
    "SUBMITTED_STATUSES",
    "compute_project_stage",
]
