"""gpu_allocations 增加卡位追溯字段。

背景（docs/09 §5.6、docs/13 §4.4）：

* 卡位是调度的最小单位，但**卡位互斥不进数据库**——`docs/04` 数据模型明确
  38 张表里没有 slot 表，互斥由 ``slots.yaml`` 静态声明 + Agent 单队列 +
  本表既有的活动租约唯一索引（``uq_gpu_allocations_active_device``）三层保证。
* 因此本次只**新增观测与追溯字段**，不新增任何唯一约束或排他索引：
  出问题时能回答「这个任务跑在哪台机器的哪个卡位、用的什么镜像、走哪个 Agent」，
  对应 `docs/01` §11.2 六类追溯元数据里的「执行环境」与 `docs/12` 的追溯验收。

Revision ID: 20261026_04
Revises: 20261026_03
Create Date: 2026-10-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20261026_04"
down_revision = "20261026_03"
branch_labels = None
depends_on = None

TABLE_NAME = "gpu_allocations"

ADDED_COLUMNS: tuple[tuple[str, sa.types.TypeEngine, str | None], ...] = (
    ("slot_id", sa.String(length=64), None),
    ("accelerator_model", sa.String(length=64), None),
    ("accelerator_vendor", sa.String(length=32), None),
    ("device_ids", sa.String(length=128), None),
    ("agent_endpoint", sa.String(length=255), None),
    ("image_ref", sa.String(length=255), None),
)

ADDED_INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ix_gpu_allocations_slot_id", ("slot_id",)),
)


def _existing_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(TABLE_NAME)}


def _existing_indexes() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(TABLE_NAME)}


def upgrade() -> None:
    table_names = set(sa.inspect(op.get_bind()).get_table_names())
    if TABLE_NAME not in table_names:
        return

    existing = _existing_columns()
    for name, column_type, default in ADDED_COLUMNS:
        if name in existing:
            continue
        op.add_column(
            TABLE_NAME,
            sa.Column(name, column_type, nullable=True, server_default=default),
        )

    indexes = _existing_indexes()
    for index_name, columns in ADDED_INDEXES:
        if index_name in indexes:
            continue
        op.create_index(index_name, TABLE_NAME, list(columns))


def downgrade() -> None:
    table_names = set(sa.inspect(op.get_bind()).get_table_names())
    if TABLE_NAME not in table_names:
        return

    indexes = _existing_indexes()
    for index_name, _columns in ADDED_INDEXES:
        if index_name in indexes:
            op.drop_index(index_name, table_name=TABLE_NAME)

    existing = _existing_columns()
    for name, _column_type, _default in ADDED_COLUMNS:
        if name in existing:
            op.drop_column(TABLE_NAME, name)
