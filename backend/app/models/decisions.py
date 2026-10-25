"""研发决策记录（只追加）— docs/04 §9.5，docs/03 §3.6.2。

平台原来只能「跑完计算」，无法承载研发最核心的动作：**决定哪个候选往下走**。
两张表把这件动作沉淀成研发资产：

* ``decision_records`` — 一次决策：决策点（DP1~DP5）、决策对象、依据（任务 +
  当时指标）、结论理由、决策人与时间。
* ``decision_items`` — 该次决策的**成员快照**（入选/淘汰 + 当时的评分与排名）。

**为什么必须快照**：候选集合后续会被修改（``candidate_set_items`` 可以增删、
候选物的 ``design_score`` 会随重算变化）。若只存引用，半年后回看决策记录会看到
一组与当时完全不同的数据，追溯链就断了。``decision_items`` 与
``candidate_set_items.snapshot_score`` 是同一个语义。

两张表都是**只追加**（docs/10 DB-09，与 ``audit_logs`` 同级别）：ORM 层用事件守卫
把 ``UPDATE``/``DELETE`` 变成立即报错的编程错误，生产环境再用窄授权兜底。

**索引只在这里声明**（``__table_args__``），列上不再写 ``index=True``：两处并存会
让 ``Base.metadata.create_all``（开发/测试）与 Alembic（生产）得到不同的索引集，
而这种漂移只在生产才暴露。
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin, utcnow
from app.models.traceability import ImmutableRecordError

#: 决策点（docs/03 §3.6.2）：DP1 靶点是否推进 → DP5 最终推荐进入实验。
DECISION_POINTS = ("DP1", "DP2", "DP3", "DP4", "DP5")

#: 决策对象类型。``CANDIDATE_SET`` 额外校验成员快照归属（其余三类校验候选物归属）。
DECISION_SUBJECT_TYPES = ("TARGET", "POCKET", "CANDIDATE_SET", "STRUCTURE")

#: 决策结论。
DECISION_VERDICTS = ("SELECTED", "EXCLUDED")

#: 快照里「没有录到分」的标记。缺失写成 ``None`` 且打上这个标记，读者才知道这一行
#: 是「当时没记录」而不是「当时为 0」——只追加表里两者一旦混淆就再也分不开。
SCORE_SOURCE_MISSING = "missing"


class DecisionRecord(Base, UUIDMixin, TimestampMixin):
    """决策记录（只追加）— docs/04 §9.5。"""

    __tablename__ = "decision_records"
    __table_args__ = (
        # 列表页唯一的筛选组合（项目 + 决策点筛选）。
        Index("ix_decision_records_project_point", "project_id", "decision_point"),
        # 列表排序键；不带它时 PostgreSQL 会对倒序分页做全表排序。
        Index("ix_decision_records_project_decided", "project_id", "decided_at"),
        # 反查「这个靶点/口袋/候选集被决策过几次」。
        Index("ix_decision_records_subject_id", "subject_id"),
    )

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    decision_point = Column(String(8), nullable=False)
    subject_type = Column(String(32), nullable=False)
    subject_id = Column(String(36), nullable=False)
    reason = Column(Text, nullable=False)
    basis_task_ids = Column(JSON, nullable=False, default=list)
    basis_metrics = Column(JSON, nullable=False, default=dict)
    #: 决策人快照：用户改名或停用后，记录仍要可读（与 ``audit_logs.actor`` 同理）。
    #: 长度按 ``docs/04`` §9.5 的 ``varchar(64)``；``users.email`` 是 255，所以写入
    #: 时必须截断（否则超长邮箱在 PostgreSQL 上直接 500，SQLite 只是默默塞进去）。
    decided_by = Column(String(64), nullable=False)
    decided_by_id = Column(String(36), nullable=True)
    decided_at = Column(DateTime, nullable=False, default=utcnow)

    items = relationship(
        "DecisionItem",
        back_populates="decision",
        cascade="all, delete-orphan",
        # 次级键 ``candidate_id``：``snapshot_rank`` 允许为空且可能重复，
        # 只按它排序时 SQLite（NULLS FIRST）与 PostgreSQL（NULLS LAST）顺序不同，
        # 派生出的 ``selected_ids`` 会随部署的数据库而变。
        order_by="[DecisionItem.snapshot_rank, DecisionItem.candidate_id]",
    )


class DecisionItem(Base, UUIDMixin):
    """决策成员快照（只追加）— docs/04 §9.5。"""

    __tablename__ = "decision_items"
    __table_args__ = (
        UniqueConstraint(
            "decision_id",
            "candidate_id",
            name="uq_decision_items_decision_candidate",
        ),
        Index("ix_decision_items_decision_verdict", "decision_id", "verdict"),
    )

    decision_id = Column(
        String(36), ForeignKey("decision_records.id"), nullable=False
    )
    #: 非空：``UniqueConstraint`` 不约束 NULL，允许空值等于允许「没有候选物的快照行」。
    candidate_id = Column(String(36), nullable=False)
    verdict = Column(String(16), nullable=False)
    snapshot_score = Column(Numeric(10, 4), nullable=True)
    snapshot_rank = Column(Integer, nullable=True)
    snapshot_attrs = Column(JSON, nullable=False, default=dict)

    decision = relationship("DecisionRecord", back_populates="items")


def _reject_mutation(*_args: object, **_kwargs: object) -> None:
    raise ImmutableRecordError(
        "只追加表禁止更新或删除（docs/10 DB-09：decision_records 与 decision_items）"
    )


# ``Session.merge`` 与批量 ``update()``/``delete()`` 都不在这里兜底：前者会触发
# UPDATE（已被守卫拦下），后两者绕过 ORM 事件，由评审清单与窄授权负责。
for _model in (DecisionRecord, DecisionItem):
    for _event_name in ("before_update", "before_delete"):
        event.listen(_model, _event_name, _reject_mutation)


__all__ = [
    "DECISION_POINTS",
    "DECISION_SUBJECT_TYPES",
    "DECISION_VERDICTS",
    "SCORE_SOURCE_MISSING",
    "DecisionItem",
    "DecisionRecord",
]
