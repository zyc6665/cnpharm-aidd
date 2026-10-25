"""研发决策记录的领域服务（docs/04 §9.5，docs/05 §3.3，docs/03 §3.6.2）。

HTTP 层只负责权限与响应包装，真正的规则在这里：

* **归属校验**：``subject_type == "CANDIDATE_SET"`` 时，快照里的每个
  ``candidate_id`` 必须是该集合的成员。否则一条决策记录可以宣称「我选了 100 个
  候选物」，而集合里只有 3 个——记录一旦只追加就永远无法纠正。
* **成员快照入库**：把 ``selected_ids``/``excluded_ids`` 与 ``snapshot`` 合并成
  ``decision_items``，每行带决策当时的评分与排名。候选集合后续被改写不影响历史。
* **审计**：写入同时追加 ``audit_logs``（与 ``docs/04`` §9.5 的权限段一致）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import NotFoundException, ValidationException
from app.common.time import utcnow
from app.logging.audit import AuditAction, ResourceType, get_audit_logger
from app.models.compounds import CandidateSetItem
from app.models.decisions import DecisionItem, DecisionRecord
from app.models.users import User
from app.schemas.decisions import DecisionCreate
from app.services.domain_compounds import load_candidate_set
from app.services.domain_targets import (
    load_pocket,
    load_structure,
    load_target,
    structure_target,
)
from app.services.project_access import require_project_role

#: 读：项目内全员（含 viewer）。决策记录是项目结论，成员都应该看得到。
DECISION_READ_ROLES = ("owner", "editor", "runner", "viewer")

#: 写：viewer 不能替项目做决策（docs/05 §3.3「需项目角色 ≥ MEMBER」）。
DECISION_WRITE_ROLES = ("owner", "editor", "runner")


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def serialize_decision(record: DecisionRecord) -> dict:
    """Serialize one decision record with its member snapshot.

    ``items`` 是成员快照，``selected_ids``/``excluded_ids`` 由它派生——两处不能各
    自为政，否则前端要判断哪个才是权威。
    """
    items = [
        {
            "candidate_id": item.candidate_id,
            "verdict": item.verdict,
            "snapshot_score": _number(item.snapshot_score),
            "snapshot_rank": item.snapshot_rank,
            "snapshot_attrs": item.snapshot_attrs or {},
        }
        for item in (record.items or [])
    ]
    return {
        "id": record.id,
        "project_id": record.project_id,
        "decision_point": record.decision_point,
        "subject_type": record.subject_type,
        "subject_id": record.subject_id,
        "reason": record.reason,
        "basis_task_ids": record.basis_task_ids or [],
        "basis_metrics": record.basis_metrics or {},
        "decided_by": record.decided_by,
        "decided_by_id": record.decided_by_id,
        "decided_at": _iso(record.decided_at),
        "created_at": _iso(record.created_at),
        "selected_ids": [i["candidate_id"] for i in items if i["verdict"] == "SELECTED"],
        "excluded_ids": [i["candidate_id"] for i in items if i["verdict"] == "EXCLUDED"],
        "items": items,
    }


async def _subject_project_id(
    db: AsyncSession, *, subject_type: str, subject_id: str
) -> str:
    """Resolve the owning project of a decision subject.

    决策对象必须真的属于这个项目；否则 ``/projects/A/decisions`` 可以为 B 项目的
    候选集写记录，跨项目引用把权限模型绕过去了。
    """
    if subject_type == "CANDIDATE_SET":
        candidate_set = await load_candidate_set(db, subject_id)
        return str(candidate_set.project_id)
    if subject_type == "TARGET":
        target = await load_target(db, subject_id)
        return str(target.project_id)
    if subject_type == "POCKET":
        pocket = await load_pocket(db, subject_id)
        target = await structure_target(db, await load_structure(db, str(pocket.structure_id)))
        return str(target.project_id)
    if subject_type == "STRUCTURE":
        structure = await load_structure(db, subject_id)
        target = await structure_target(db, structure)
        return str(target.project_id)
    # ``DecisionCreate`` 用 Literal 限定取值，走到这里说明分类被人为绕过。
    raise ValidationException(f"不支持的决策对象类型：{subject_type}")


async def _ensure_snapshot_membership(
    db: AsyncSession, *, set_id: str, snapshot_ids: list[str]
) -> None:
    rows = (
        await db.execute(
            select(CandidateSetItem.candidate_id).where(CandidateSetItem.set_id == set_id)
        )
    ).scalars().all()
    members = {str(value) for value in rows}
    strangers = [value for value in snapshot_ids if value not in members]
    if strangers:
        raise ValidationException(
            "快照中有候选物不属于该候选集合：" + "、".join(strangers),
            detail={"candidate_ids": strangers, "set_id": set_id},
        )


async def create_decision(
    db: AsyncSession,
    *,
    project_id: str,
    user: User,
    data: DecisionCreate,
) -> DecisionRecord:
    await require_project_role(
        db,
        project_id=project_id,
        user=user,
        allowed_roles=DECISION_WRITE_ROLES,
    )

    owner_project_id = await _subject_project_id(
        db, subject_type=data.subject_type, subject_id=data.subject_id
    )
    if owner_project_id != project_id:
        raise NotFoundException("决策对象不存在")

    snapshot_ids = [item.candidate_id for item in data.snapshot]
    if data.subject_type == "CANDIDATE_SET":
        await _ensure_snapshot_membership(
            db, set_id=data.subject_id, snapshot_ids=snapshot_ids
        )

    selected = set(data.selected_ids)
    verdicts = {
        candidate_id: ("SELECTED" if candidate_id in selected else "EXCLUDED")
        for candidate_id in snapshot_ids
    }
    score_by_id = {item.candidate_id: item for item in data.snapshot}

    record = DecisionRecord(
        project_id=project_id,
        decision_point=data.decision_point,
        subject_type=data.subject_type,
        subject_id=data.subject_id,
        reason=data.reason.strip(),
        basis_task_ids=list(data.basis_task_ids),
        basis_metrics=dict(data.basis_metrics),
        decided_by=user.email or user.display_name or str(user.id),
        decided_by_id=str(user.id),
        decided_at=utcnow(),
    )
    for candidate_id in snapshot_ids:
        snapshot = score_by_id[candidate_id]
        record.items.append(
            DecisionItem(
                candidate_id=candidate_id,
                verdict=verdicts[candidate_id],
                snapshot_score=snapshot.score,
                snapshot_rank=snapshot.rank,
                snapshot_attrs={},
            )
        )

    db.add(record)
    await db.commit()

    # 重新用 selectinload 取回：异步会话下访问未预加载的关系会抛 ``MissingGreenlet``，
    # 而序列化要读 ``items``（docs/04 §5.6 的约定）。
    stored = (
        await db.execute(
            select(DecisionRecord)
            .options(selectinload(DecisionRecord.items))
            .where(DecisionRecord.id == record.id)
        )
    ).scalar_one()

    get_audit_logger().log_data_access(
        user_id=str(user.id),
        resource_type=ResourceType.DECISION_RECORD,
        resource_id=str(stored.id),
        action=AuditAction.DECISION_CREATE,
        user_email=user.email,
        project_id=str(project_id),
        decision_point=stored.decision_point,
        subject_type=stored.subject_type,
        subject_id=str(stored.subject_id),
    )
    return stored


async def list_decisions(
    db: AsyncSession,
    *,
    project_id: str,
    page: int,
    page_size: int,
    decision_point: str | None = None,
) -> tuple[list[DecisionRecord], int]:
    conditions = [DecisionRecord.project_id == project_id]
    if decision_point:
        conditions.append(DecisionRecord.decision_point == decision_point)

    total = (
        await db.execute(select(func.count()).select_from(DecisionRecord).where(*conditions))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(DecisionRecord)
                .options(selectinload(DecisionRecord.items))
                .where(*conditions)
                .order_by(DecisionRecord.decided_at.desc(), DecisionRecord.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total or 0)


__all__ = [
    "DECISION_READ_ROLES",
    "DECISION_WRITE_ROLES",
    "create_decision",
    "list_decisions",
    "serialize_decision",
]
