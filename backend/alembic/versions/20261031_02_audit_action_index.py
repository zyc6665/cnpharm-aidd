"""审计日志补 ``(action, created_at)`` 复合索引

背景（docs/20 §1 实测）：审计日志页的主查询是
``WHERE action = ? AND created_at >= ? ORDER BY created_at DESC LIMIT 50``。
改造前它走单列 ``ix_audit_logs_action`` 再 ``USE TEMP B-TREE FOR ORDER BY``，
12 万行时 **51.07 ms**；补上 ``(action, created_at)`` 后 **0.69 ms**，约 74×。

为什么不并进 ``20261031_01``：那一版按"批量建索引"编排，审计表是只追加的高写入
表，索引增减要与其它表的收敛分开观察（建完看写入延迟有没有抬升）。单独一个迁移
也让"哪些索引是本期新增、影响哪张表"在 ``alembic history`` 里一眼可查。

索引数约束：``test/test_index_governance.py`` 要求 ``audit_logs`` 上的索引 ≤ 7。
本迁移执行后为 6+1=7（前面已删掉 actor / resource_type / result / actor_id 四个
单列索引，见 ``20261031_01``）。

Revision ID: 20261031_02
Revises: 20261031_01
Create Date: 2026-10-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261031_02"
down_revision = "20261031_01"
branch_labels = None
depends_on = None


TABLE = "audit_logs"
INDEX = "ix_audit_logs_action_created"
COLUMNS = ["action", "created_at"]


def _table_exists() -> bool:
    return TABLE in sa.inspect(op.get_bind()).get_table_names()


def _index_names() -> set[str]:
    """返回 ``audit_logs`` 上已有的索引名。

    必须容忍表不存在：``test_alembic_migration_dry_run`` 与
    ``test_task_project_aggregate`` 会在**中途某个旧 revision** 建库后直接
    ``upgrade head``，那条路径上 ``audit_logs`` 还没建出来，反射会抛
    ``NoSuchTableError``。表不存在时没什么可加，直接跳过。
    """
    if not _table_exists():
        return set()
    bind = op.get_bind()
    return {item["name"] for item in sa.inspect(bind).get_indexes(TABLE)}


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _table_exists() or INDEX in _index_names():
        return
    if _is_postgresql():
        # 只追加的高写入表，必须 CONCURRENTLY 建，否则 SHARE 锁会把审计写入挡在后面。
        with op.get_context().autocommit_block():
            op.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{INDEX}" '
                f'ON "{TABLE}" (action, created_at)'
            )
    else:
        op.create_index(INDEX, TABLE, COLUMNS)


def downgrade() -> None:
    if not _table_exists() or INDEX not in _index_names():
        return
    if _is_postgresql():
        with op.get_context().autocommit_block():
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{INDEX}"')
    else:
        op.drop_index(INDEX, table_name=TABLE)
