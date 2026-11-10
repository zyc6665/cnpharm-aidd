"""候选物与任务的双向挂接（V3.0 §4.8 归属关系、``docs/26`` H-14）。

**问题**：``GET /candidates/{id}/results`` 一直返回空列表。它的过滤条件是
``Task.extra_data["domain"]["candidate_id"]``，而全仓**没有任何写入方**——查询在等
一个从不出现的键。

**这里补的是写入侧**：提交任务时显式声明「这个任务是为某个候选物跑的」，就把候选物
身份写进任务的领域上下文（与结构预测/口袋预测写 ``domain`` 的方式一致，见
``app.services.domain_targets``）。同时提供读取侧的过滤条件构造函数，让「产出该候选物
的任务」也算它的结果——用户问「这个候选物在哪出现过」，两个方向都该算：

* **产出侧**：``Candidate.task_id``（这个候选物由哪个任务生成）；
* **消费侧**：``domain.candidate_id``（哪些任务以这个候选物为输入）。

**为什么不在提交时逐条校验任务输入里有没有这个候选物**：候选物是逻辑对象，任务的输入
是文件；从「SDF 里的某个分子」反推候选物需要分子级匹配，误判比缺失更糟（错的结果挂到
别的候选物上比查不到更难发现）。因此只认显式声明，宁可少一条也不张冠李戴。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ValidationException
from app.models.compounds import Candidate
from app.models.tasks import Task
from app.models.traceability import TaskInputSnapshot
from app.models.users import User
from app.services.domain_compounds import require_candidate_read_access

#: 任务领域上下文里表示「该任务为某个候选物而跑」的 ``kind`` 值。
DOMAIN_KIND_CANDIDATE_TASK = "candidate_task"

#: 输入快照里标记候选物来源行的实体类型。
CANDIDATE_ENTITY_TYPE = "candidate"


async def attach_candidate_domain(
    db: AsyncSession,
    *,
    extra_data: Mapping[str, Any],
    candidate_id: Optional[str],
    project_id: Optional[str],
    user: User,
) -> dict[str, Any]:
    """把候选物身份合进任务的 ``extra_data["domain"]``。

    返回新的 ``extra_data`` 字典（不改入参）。``candidate_id`` 为空时原样返回。
    """
    merged = dict(extra_data)
    if not candidate_id:
        return merged

    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise ValidationException("候选物不存在")
    await require_candidate_read_access(db, candidate=candidate, user=user)

    if not project_id:
        # 候选物属于项目；任务不属于任何项目就无法建立归属关系。
        raise ValidationException("提交候选物任务必须指定项目")
    if str(candidate.project_id) != str(project_id):
        raise ValidationException("候选物不属于该项目")

    domain = merged.get("domain")
    domain = dict(domain) if isinstance(domain, Mapping) else {}
    domain["kind"] = DOMAIN_KIND_CANDIDATE_TASK
    domain["candidateId"] = str(candidate.id)
    # 双写 snake_case：``/candidates/{id}/results`` 的 SQL 过滤读的是这个键
    # （JSON 列上的键名改一次要迁移历史行，所以两个都写，读侧只认 snake_case）。
    domain["candidate_id"] = str(candidate.id)
    merged["domain"] = domain
    return merged


def candidate_result_conditions(
    *, candidate_id: str, producing_task_id: Optional[str]
) -> ColumnElement[bool]:
    """``/candidates/{id}/results`` 的过滤条件：产出侧 ∪ 消费侧 ∪ 快照侧。"""
    conditions: list[ColumnElement[bool]] = [
        Task.extra_data["domain"]["candidate_id"].as_string() == str(candidate_id)
    ]
    if producing_task_id:
        conditions.append(Task.id == str(producing_task_id))
    snapshot_task_ids = select(TaskInputSnapshot.task_id).where(
        TaskInputSnapshot.entity_type == CANDIDATE_ENTITY_TYPE,
        TaskInputSnapshot.entity_id == str(candidate_id),
    )
    conditions.append(Task.id.in_(snapshot_task_ids))
    return or_(*conditions)
