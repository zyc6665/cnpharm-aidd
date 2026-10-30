"""研发阶段纯推导（docs/05 §3.2，docs/03 §3.6.1）。

**为什么不加 ``project.stage`` 字段**：阶段是数据的投影，不是数据本身。一旦落库，
用户新建靶点后就出现「库里写 S1、实际已经到 S2」的分歧，而唯一的修法是让每个写
路径都记得回填——那正是这类字段最终都变成脏数据的路径。这里每次 GET 现算，允许
回退（删掉最后一个靶点就退回 S0），不阻塞任何操作。

阶段是**导航与提示**，不是门禁：``gaps`` 列出当前阶段「还差什么」，调用方拿它渲染
下一步提示，但任何接口都不因 ``gaps`` 非空而拒绝写入。

## 与 ``docs/03`` §3.6.1 的判定条件差异（有意的简化）

| 阶段 | ``docs/03`` 的进入条件 | 本实现的近似 |
|---|---|---|
| S1 | 至少 1 个靶点 **+ 序列或结构** | 只数 ``targets``：本项目里没有序列的靶点只是占位，把它挡在 S1 外会让「刚建完靶点」的用户看不到任何进度反馈 |
| S2 | 1 个结构 + 1 个**已选定**口袋 | 一致（``pockets.selected``） |
| S3 | 候选集合非空 | 数 ``candidates``（候选物本体）：候选集合可以建了又清空，候选物才是产物 |
| S4 | 候选集有 ADMET/亲和力结果 | 「本项目提交过计算任务」：结果表按任务产出，在阶段这一层解析任务产物要额外 join 5 张表，而「提交过任务」在数据上必然先于「有结果」 |
| S5 | 候选集有对接/MD/自由能结果 | 「本项目有成功结束的任务」（``TaskStatus.SUCCESS``） |
| S6 | 至少 1 条决策记录 | 一致（``decision_records``） |

## 已知的契约偏离（计划内已记录）

* **``stageReachedAt`` 不实现**：它需要「阶段首次达成时间」的追溯，依赖任务历史与
  逐阶段的时间下界，属后续 PR；本接口只回答「现在在哪」。
* **``counters`` 是超集字段**：比 ``docs/05`` §3.2 的示例多 7 个计数，前端 P-04 的
  统计卡直接复用，少一次请求。多字段对前端是兼容变更。

## 性能

当前是 7 条独立 ``count(*)``，其中任务的 ``extra_data->>'project_id'`` 是 JSON
表达式，无法走索引。项目数据量级（≤ 数千任务）下这是可接受的；若后续变慢，优先给
``extra_data->>'project_id'`` 建 functional index，而不是把计数合并成一次全表扫描。
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
    "S6": "决策与归档",
}

#: 顺序即优先级：``gaps`` 先报挡住整条链路的那一条。最多给 5 条——再多就不是
#: 「下一步做什么」，而是一份让人不想读的待办清单。
GAP_ORDER = (
    "NO_TARGET",
    "NO_STRUCTURE",
    "NO_POCKET_SELECTED",
    "NO_CANDIDATE",
    "NO_TASK",
    "NO_DECISION",
)

#: 一条任务到达这里才算「结果可看」；排队与运行中仍属于「已提交」。
#: 失败/超时/取消没有结果可看，故不进入 FINISHED_STATUSES。
FINISHED_STATUSES = (TaskStatus.SUCCESS.value,)
#: 「已提交」= 除 PENDING 之外的全部状态：PENDING 是刚创建、尚未入队调度，
#: 不算用户提交过；其余七态（QUEUED/RUNNING/SUCCESS/FAILURE/TIMEOUT/CANCELED/
#: REJECTED）都代表用户确实提交过任务。这里用集合推导而不是手写清单，避免
#: 状态机再扩态时又漏改——漏掉的后果是「任务全部失败/超时」的项目从 S4 掉回
#: S3 并误报 NO_TASK（「还没有提交过计算任务」）。
SUBMITTED_STATUSES = tuple(
    status.value for status in TaskStatus if status is not TaskStatus.PENDING
)

#: ``gaps[].link`` 指向 ``docs/06`` 里已定义的页面路由（P-06/P-09~P-11/P-18/P-31/
#: P-39）。没有对应页面时给 ``None``，前端据此决定是否渲染跳转按钮。
GAP_LINKS = {
    "NO_TARGET": "/projects/{project_id}/targets",
    "NO_STRUCTURE": "/projects/{project_id}/targets",
    "NO_POCKET_SELECTED": "/projects/{project_id}/targets",
    "NO_CANDIDATE": "/projects/{project_id}/candidates",
    "NO_TASK": "/tasks",
    "NO_DECISION": "/projects/{project_id}/decisions",
}

MAX_GAPS = 5


def _gap(project_id: str, *, code: str, message: str, action: str) -> dict:
    link_template = GAP_LINKS.get(code)
    return {
        "code": code,
        "message": message,
        "action": action,
        "link": link_template.format(project_id=project_id) if link_template else None,
    }


async def _count(db: AsyncSession, statement) -> int:
    return int((await db.execute(statement)).scalar_one() or 0)


async def compute_project_stage(db: AsyncSession, *, project_id: str) -> dict:
    """Derive the project stage from its data; never writes.

    ``S0 项目已建`` → ``S1 靶点已建`` → ``S2 结构与口袋就绪`` → ``S3 候选物已生成``
    → ``S4 已提交计算`` → ``S5 已有结果`` → ``S6 已有决策记录``。
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
    decision_count = await _count(
        db,
        select(func.count())
        .select_from(DecisionRecord)
        .where(DecisionRecord.project_id == project_id),
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
    if len(reached) == 6 and decision_count > 0:
        reached.append("S6")

    current_stage = reached[-1]
    next_stage = (
        f"S{int(current_stage[1:]) + 1}" if current_stage != "S6" else None
    )

    gaps: list[dict] = []
    if target_count == 0:
        gaps.append(
            _gap(
                project_id,
                code="NO_TARGET",
                message="项目还没有靶点",
                action="前往靶点与结构页新建靶点",
            )
        )
    if target_count > 0 and structure_count == 0:
        gaps.append(
            _gap(
                project_id,
                code="NO_STRUCTURE",
                message=f"已有 {target_count} 个靶点，但还没有导入结构",
                action="在蛋白详情导入 PDB 结构或提交结构预测任务",
            )
        )
    if structure_count > 0 and selected_pocket_count == 0:
        gaps.append(
            _gap(
                project_id,
                code="NO_POCKET_SELECTED",
                message=f"已有 {structure_count} 个结构，但尚未选定口袋",
                action="前往结构详情选择口袋",
            )
        )
    if len(reached) >= 3 and candidate_count == 0:
        gaps.append(
            _gap(
                project_id,
                code="NO_CANDIDATE",
                message="结构与口袋已就绪，但还没有候选物",
                action="提交候选生成任务，或手工录入候选物",
            )
        )
    if len(reached) >= 4 and submitted_task_count == 0:
        gaps.append(
            _gap(
                project_id,
                code="NO_TASK",
                message="已有候选物，但还没有提交过计算任务",
                action="在候选物页选择候选并提交评估任务",
            )
        )
    if len(reached) >= 6 and decision_count == 0:
        gaps.append(
            _gap(
                project_id,
                code="NO_DECISION",
                message="已有计算结果，但还没有记录任何研发决策",
                action="在结果页选择候选并提交决策记录",
            )
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
        "gaps": ordered[:MAX_GAPS],
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
    "GAP_LINKS",
    "GAP_ORDER",
    "MAX_GAPS",
    "STAGE_NAMES",
    "SUBMITTED_STATUSES",
    "compute_project_stage",
]
