"""研发决策记录的领域服务（docs/04 §9.5，docs/05 §3.3，docs/03 §3.6.2）。

HTTP 层只负责权限与响应包装，真正的规则在这里：

* **归属校验**：``subject_type == "CANDIDATE_SET"`` 时，快照里的每个
  ``candidate_id`` 必须是该集合的成员；其余三种对象类型（靶点/口袋/结构）没有
  「成员」概念，但快照里引用的候选物仍必须是**本项目**的候选物。否则一条决策记录
  可以宣称「我选了 100 个候选物」，或引用别的项目的候选 UUID——记录一旦只追加就
  永远无法纠正，跨项目引用还顺手把权限模型绕过去了。
* **成员快照入库**：把 ``selected_ids``/``excluded_ids`` 与 ``snapshot`` 合并成
  ``decision_items``，每行带决策当时的评分与排名。候选集合后续被改写不影响历史。
  结论里的每个 id 都必然落成一行：没录到分的补 ``score=None`` 并标记
  ``score_source="missing"``，保证「返回的结论 == 提交的结论」。
* **审计**：写入同时追加 ``audit_logs``（与 ``docs/04`` §9.5 的权限段一致）。
  审计按 ``docs/04`` §3.2.2 是**最终一致**的旁路：它失败不能把已经提交的数据变成
  客户端眼里的 500。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import NotFoundException, ValidationException
from app.common.time import utcnow
from app.logging.audit import (
    AuditAction,
    AuditEvent,
    AuditResult,
    ResourceType,
    get_audit_logger,
)
from app.models.compounds import Candidate, CandidateSetItem
from app.models.decisions import SCORE_SOURCE_MISSING, DecisionItem, DecisionRecord
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

logger = logging.getLogger(__name__)

#: 读：项目内全员（含 viewer）。决策记录是项目结论，成员都应该看得到。
DECISION_READ_ROLES = ("owner", "editor", "runner", "viewer")

#: 写：需项目角色 ≥ MEMBER（docs/04 §9.5「权限」末段）。仓库里 ``runner`` 低于
#: ``editor``（见 ``domain_compounds.WRITE_ROLES``），能跑任务不等于能替项目拍板。
DECISION_WRITE_ROLES = ("owner", "editor")

#: ``decided_by`` 是 ``varchar(64)``（docs/04 §9.5），而 ``users.email`` 是 255。
DECIDED_BY_MAX_LENGTH = 64


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


async def _ensure_candidates_in_project(
    db: AsyncSession, *, project_id: str, candidate_ids: list[str]
) -> None:
    """非 ``CANDIDATE_SET`` 的决策：快照里的候选物必须属于本项目。

    这三种对象类型没有「成员集合」可查，于是此前``candidate_id`` 是任意字符串，
    能把别的项目的候选 UUID 写进只追加表。这里只证明「这些候选物是本人的项目里的」，
    不去判断它们与靶点/口袋的业务关联——那层语义由前端选择器保证，服务端兜底的是
    权限边界。
    """
    if not candidate_ids:
        return
    rows = (
        await db.execute(
            select(Candidate.id).where(
                Candidate.id.in_(candidate_ids),
                Candidate.project_id == project_id,
            )
        )
    ).scalars().all()
    known = {str(value) for value in rows}
    strangers = [value for value in candidate_ids if value not in known]
    if strangers:
        raise ValidationException(
            "快照中有候选物不属于该项目：" + "、".join(strangers),
            detail={"candidate_ids": strangers, "project_id": project_id},
        )


def _emit_decision_audit(*, user: User, record: DecisionRecord) -> None:
    """Append one ``DECISION_CREATE`` audit event.

    直接构造 ``AuditEvent`` 而不是走 ``log_data_access``：后者没有 ``user_email``
    形参，``user_email=`` 会落进 ``**extra``，``event.user_email`` 仍为 ``None``，
    最终 ``audit_logs.actor`` 退化成用户 UUID，而 ``docs/04`` §3 要求 actor 是
    用户名快照（用户改名/停用后审计仍可读）。
    """
    event = AuditEvent(
        action=AuditAction.DECISION_CREATE,
        result=AuditResult.SUCCESS,
        user_id=str(user.id),
        user_email=user.email,
        user_role=user.role,
        resource_type=ResourceType.DECISION_RECORD,
        resource_id=str(record.id),
        extra={
            "project_id": str(record.project_id),
            "decision_point": record.decision_point,
            "subject_type": record.subject_type,
            "subject_id": str(record.subject_id),
        },
    )
    get_audit_logger().log(event)


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
    else:
        await _ensure_candidates_in_project(
            db,
            project_id=project_id,
            candidate_ids=list(
                dict.fromkeys([*data.selected_ids, *data.excluded_ids, *snapshot_ids])
            ),
        )

    # 结论是权威：``selected_ids``/``excluded_ids`` 里的每个 id 都要落成一行 item，
    # 否则 ``serialize_decision`` 由 items 派生出的结论会与提交的结论不一致，而只追加
    # 表没有第二次机会纠正。缺分的结论补 ``score=None`` + ``score_source="missing"``。
    verdicts: list[tuple[str, str]] = [
        (candidate_id, "SELECTED") for candidate_id in data.selected_ids
    ] + [(candidate_id, "EXCLUDED") for candidate_id in data.excluded_ids]
    snapshot_by_id = {item.candidate_id: item for item in data.snapshot}

    decided_by = (user.email or user.display_name or str(user.id))[:DECIDED_BY_MAX_LENGTH]
    record = DecisionRecord(
        project_id=project_id,
        decision_point=data.decision_point,
        subject_type=data.subject_type,
        subject_id=data.subject_id,
        reason=data.reason.strip(),
        basis_task_ids=list(data.basis_task_ids),
        basis_metrics=dict(data.basis_metrics),
        decided_by=decided_by,
        decided_by_id=str(user.id),
        decided_at=utcnow(),
    )
    for candidate_id, verdict in verdicts:
        snapshot = snapshot_by_id.get(candidate_id)
        record.items.append(
            DecisionItem(
                candidate_id=candidate_id,
                verdict=verdict,
                snapshot_score=snapshot.score if snapshot else None,
                snapshot_rank=snapshot.rank if snapshot else None,
                snapshot_attrs={} if snapshot else {"score_source": SCORE_SOURCE_MISSING},
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

    # 审计是最终一致的旁路（docs/04 §3.2.2）：数据此时已提交，审计写失败只能记日志，
    # 不能反过来让客户端看到一个「其实已经成功」的 500。
    try:
        _emit_decision_audit(user=user, record=stored)
    except Exception:  # noqa: BLE001 - 审计失败不得影响业务结果
        logger.warning(
            "决策记录 %s 已写入，但审计事件写入失败", stored.id, exc_info=True
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
                # 次级键 ``id``：``decided_at`` 精度不足以区分同一秒写入的两条记录，
                # 只按时间排序时分页会出现重复行或漏行。
                .order_by(
                    DecisionRecord.decided_at.desc(),
                    DecisionRecord.created_at.desc(),
                    DecisionRecord.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total or 0)


__all__ = [
    "DECIDED_BY_MAX_LENGTH",
    "DECISION_READ_ROLES",
    "DECISION_WRITE_ROLES",
    "create_decision",
    "list_decisions",
    "serialize_decision",
]
