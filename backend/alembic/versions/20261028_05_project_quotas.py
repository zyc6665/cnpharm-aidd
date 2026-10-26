"""project_quotas：项目算力配额（docs/04 §5.3、docs/03 §5.6.3③、docs/05 §3/§9）

G-9 要的是「项目级算力分配可预期」：并发 DCU、并发 CPU 任务、周期算力分钟
三条上限 + 单任务时长上限 + 超额告警阈值。这张表只存**配置与账本快照**，
真正的用量核销写在任务 `extra_data["cost"]` 里（避免热点行更新），
`daily_quota_minutes` 的当期累计由 `app.services.project_quotas.project_usage_minutes`
按任务表聚合算出。

建表要点
--------
* **`project_id` 唯一索引**：一个项目一份配额，`get_or_create` 靠它做幂等；
  唯一性交给数据库，应用层「先查后插」在并发首次 PUT 下会插出两行。
* **`daily_quota_minutes` 默认 0 = 不限**：存量项目升级后不该突然被卡住。
  同理并发上限默认取宽松值（2 并 DCU / 10 CPU 任务），只有显式配过才收紧。
* **`overdraft_ratio` 用 `NUMERIC(4,2)`**：`1.20` 这类比例必须精确比较，
  float 在 `used == limit * ratio` 的边界上会抖动，导致同一个用量时拦时不拦。
* `updated_by` 不建外键：用户被删后仍要能回答「这份配额是谁定的」。
* 时间列用 `sa.DateTime()` 无时区，与既有表（`projects.created_at` 等）一致；
  写出时统一走 `app.common.time.utcnow`，序列化走 `isoformat_utc`。

Revision ID: 20261028_05
Revises: 20261028_04
Create Date: 2026-10-28

幂等判断
--------
``_existing_tables()`` / ``_index_names()`` 保证重复执行安全：表或索引已存在时跳过，
不会因为「开发环境已经由 ``Base.metadata.create_all`` 建过」而报 ``table already
exists``。downgrade 逆序 drop 索引再 drop 表。

.. note::
   本分支初版基于 ``20261028_03``；G-11（``20261028_04_data_versions``）先合入
   main 后，``down_revision`` 已改为 ``"20261028_04"``，迁移链为
   ``_03 → _04 → _05`` 单头。本表的迁移内容与 _04 无关，只是排队顺序变了。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261028_05"
down_revision = "20261028_04"
branch_labels = None
depends_on = None


PROJECT_QUOTAS = "project_quotas"
PROJECT_ID_INDEX = "ix_project_quotas_project_id"


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table_name: str) -> set[str]:
    if table_name not in _existing_tables():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_project_quotas_table() -> None:
    if PROJECT_QUOTAS in _existing_tables():
        return
    op.create_table(
        PROJECT_QUOTAS,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column(
            "max_concurrent_dcu", sa.Integer(), nullable=False, server_default="2"
        ),
        sa.Column(
            "max_concurrent_cpu_tasks",
            sa.Integer(),
            nullable=False,
            server_default="10",
        ),
        # 0 = 不限（存量项目升级后保持原行为）。
        sa.Column(
            "daily_quota_minutes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "max_single_task_minutes",
            sa.Integer(),
            nullable=False,
            server_default="1440",
        ),
        sa.Column(
            "quota_period",
            sa.String(length=16),
            nullable=False,
            server_default="DAILY",
        ),
        # 超额告警阈值：1.00 = 用完即告警，1.20 = 允许超 20% 后告警。
        sa.Column(
            "overdraft_ratio",
            sa.Numeric(precision=4, scale=2),
            nullable=False,
            server_default="1.00",
        ),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def upgrade() -> None:
    _create_project_quotas_table()
    if PROJECT_ID_INDEX not in _index_names(PROJECT_QUOTAS):
        op.create_index(PROJECT_ID_INDEX, PROJECT_QUOTAS, ["project_id"], unique=True)


def downgrade() -> None:
    if PROJECT_QUOTAS not in _existing_tables():
        return
    # 先撤二级索引再撤表（主键索引随表一起消失）。
    if PROJECT_ID_INDEX in _index_names(PROJECT_QUOTAS):
        op.drop_index(PROJECT_ID_INDEX, table_name=PROJECT_QUOTAS)
    op.drop_table(PROJECT_QUOTAS)
