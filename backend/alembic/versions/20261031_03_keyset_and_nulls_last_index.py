"""补齐游标翻页所需的 ``(created_at, id)`` 索引，并在 PostgreSQL 上把
``ix_tasks_project_status_finished`` 重建为 ``DESC NULLS LAST``。

背景（真 PostgreSQL 上量测后才发现，SQLite 上完全看不出来）：

1. **``NULLS LAST`` 在 PostgreSQL 上没生效。** ``20261031_01`` 里写了
   ``CREATE INDEX ... (project_id, status, finished_at DESC NULLS LAST, created_at DESC)``，
   但基线迁移 ``20260624_01`` 用 ``Base.metadata.create_all()`` 先从**模型**建了一遍
   同名索引（模型里是普通升序），``20261031_01`` 看到索引已存在就跳过了。于是空库上
   跑完迁移得到的是普通升序索引，``ORDER BY finished_at DESC NULLS LAST`` 仍然带
   ``top-N heapsort``。20 万行实测：4.5 ms（走普通索引 + 排序）而不是预期的 ~0.5 ms。
   —— 这是 v1.22 记过的「模型声明 vs 迁移建表」双真源问题**第三次**咬人。

2. **游标翻页缺索引。** ``keyset`` 用 ``(created_at, id) < (?, ?)`` 排序，但 ``tasks``
   上没有任何以 ``created_at`` 打头的索引（只有 ``(project_id, status, created_at)``
   这类带等值前缀的）。因此**不带筛选**的 ``GET /api/v1/tasks`` 游标翻页在 PostgreSQL
   上退化成 ``Parallel Seq Scan``：20 万行实测 21 ms，和展开成 ``OR`` 的写法一样慢
   —— 上了游标但没上索引，等于白上。

本迁移只补索引，不动数据。PostgreSQL 侧统一用 ``CONCURRENTLY``（包在
``autocommit_block()`` 里）避免锁表；SQLite 没有 ``CONCURRENTLY`` 与 ``NULLS LAST``
索引语法，普通建即可（SQLite 的 DESC 扫描天然把 NULL 放最后）。

Revision ID: 20261031_03
Revises: 20261031_02
Create Date: 2026-10-31
"""

import sqlalchemy as sa
from alembic import op

revision = "20261031_03"
down_revision = "20261031_02"
branch_labels = None
depends_on = None

TASKS = "tasks"
FINISHED_INDEX = "ix_tasks_project_status_finished"
CREATED_ID_INDEX = "ix_tasks_created_at_id"
FINISHED_PG_COLUMNS = (
    '"project_id", "status", "finished_at" DESC NULLS LAST, "created_at" DESC'
)


def _dialect() -> str:
    return op.get_bind().dialect.name


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {item["name"] for item in inspector.get_indexes(table)}


def _column_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {item["name"] for item in inspector.get_columns(table)}


def _rebuild_finished_index_with_nulls_last() -> None:
    """PostgreSQL：把普通升序索引换成 ``DESC NULLS LAST`` 版本。"""
    if TASKS not in _table_names():
        return
    if {"project_id", "status", "finished_at", "created_at"} - _column_names(TASKS):
        return
    with op.get_context().autocommit_block():
        op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{FINISHED_INDEX}"')
        op.execute(
            f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{FINISHED_INDEX}" '
            f'ON "{TASKS}" ({FINISHED_PG_COLUMNS})'
        )


def _create_created_at_id_index() -> None:
    """两个方言都建：游标翻页的 ``(created_at, id)`` 排序键。"""
    if TASKS not in _table_names():
        return
    if {"created_at", "id"} - _column_names(TASKS):
        return
    if CREATED_ID_INDEX in _index_names(TASKS):
        return
    if _dialect() == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{CREATED_ID_INDEX}" '
                f'ON "{TASKS}" ("created_at", "id")'
            )
        return
    op.create_index(CREATED_ID_INDEX, TASKS, ["created_at", "id"])


def upgrade() -> None:
    if _dialect() == "postgresql":
        _rebuild_finished_index_with_nulls_last()
    _create_created_at_id_index()


def downgrade() -> None:
    if TASKS in _table_names() and CREATED_ID_INDEX in _index_names(TASKS):
        if _dialect() == "postgresql":
            with op.get_context().autocommit_block():
                op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{CREATED_ID_INDEX}"')
        else:
            op.drop_index(CREATED_ID_INDEX, table_name=TASKS)
    # 降级时把 PostgreSQL 上的 finished 索引退回普通升序，与模型声明保持一致。
    if _dialect() == "postgresql" and TASKS in _table_names():
        with op.get_context().autocommit_block():
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{FINISHED_INDEX}"')
            op.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{FINISHED_INDEX}" '
                f'ON "{TASKS}" ("project_id", "status", "finished_at", "created_at")'
            )
