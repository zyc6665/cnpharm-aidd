"""Add decision_records and decision_items.

研发决策记录的存储底座（docs/04 §9.5，docs/03 §3.6.2，docs/05 §3.3）。

平台此前只能「跑完计算」，无法承载研发最核心的动作——**决定哪个候选往下走**，
于是这个结论只能写进 Excel，半年后既检索不到也追溯不到。两张表把它变成资产：

* ``decision_records`` — 一次决策（决策点 DP1~DP5、决策对象、依据、理由、人、时间）；
* ``decision_items`` — 该次决策的**成员快照**（入选/淘汰 + 当时的评分与排名）。

**为什么快照不能省**：候选集合后续会被改写（``candidate_set_items`` 可增删、
``candidates.design_score`` 会随重算变化，``candidate_sets.version`` 每改一次就 +1）。
若只存引用，回看时看到的是另一组数据，追溯链断裂。此语义与
``candidate_set_items.snapshot_score`` 一致。

两张表都是**只追加**（docs/10 DB-09，与 ``audit_logs`` 同级别）：``upgrade`` 只建表，
``downgrade`` 只删表，任何 UPDATE/DELETE 由 ORM 事件守卫拦截，生产环境再用窄授权兜底。

注意 ``(project_id, decision_point, subject_id)`` **不建唯一约束**：同一个决策点在同一
对象上允许重复决策（改主意、换一批候选），这是研发过程的常态而非错误（docs/04 §9.5 末段）。

索引口径：``project_id`` / ``decision_point`` 的单列索引被 ``(project_id,
decision_point)`` 完全覆盖，``decision_point`` / ``subject_id`` 的单列选择性也很低，
因此只保留 4 个——列表筛选组合、列表排序键、决策对象反查。索引**只在模型
``__table_args__`` 里声明**（列上不再写 ``index=True``），避免 ``create_all`` 与
Alembic 得到不同的索引集。
"""

import sqlalchemy as sa
from alembic import op


revision = "20261027_01"
down_revision = "20261026_04"
branch_labels = None
depends_on = None


TABLE_NAMES = ("decision_records", "decision_items")


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    existing = _existing_tables()

    if "decision_records" not in existing:
        op.create_table(
            "decision_records",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("project_id", sa.String(length=36), nullable=False),
            sa.Column("decision_point", sa.String(length=8), nullable=False),
            sa.Column("subject_type", sa.String(length=32), nullable=False),
            sa.Column("subject_id", sa.String(length=36), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("basis_task_ids", sa.JSON(), nullable=False),
            sa.Column("basis_metrics", sa.JSON(), nullable=False),
            sa.Column("decided_by", sa.String(length=64), nullable=False),
            sa.Column("decided_by_id", sa.String(length=36), nullable=True),
            sa.Column("decided_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        )
        op.create_index(
            "ix_decision_records_project_point",
            "decision_records",
            ["project_id", "decision_point"],
        )
        op.create_index(
            "ix_decision_records_project_decided",
            "decision_records",
            ["project_id", "decided_at"],
        )
        op.create_index("ix_decision_records_subject_id", "decision_records", ["subject_id"])

    if "decision_items" not in existing:
        op.create_table(
            "decision_items",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("decision_id", sa.String(length=36), nullable=False),
            sa.Column("candidate_id", sa.String(length=36), nullable=False),
            sa.Column("verdict", sa.String(length=16), nullable=False),
            sa.Column("snapshot_score", sa.Numeric(precision=10, scale=4), nullable=True),
            sa.Column("snapshot_rank", sa.Integer(), nullable=True),
            sa.Column("snapshot_attrs", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["decision_id"], ["decision_records.id"]),
            sa.UniqueConstraint(
                "decision_id",
                "candidate_id",
                name="uq_decision_items_decision_candidate",
            ),
        )
        op.create_index(
            "ix_decision_items_decision_verdict",
            "decision_items",
            ["decision_id", "verdict"],
        )


def downgrade() -> None:
    existing = _existing_tables()
    for table_name in reversed(TABLE_NAMES):
        if table_name in existing:
            op.drop_table(table_name)
