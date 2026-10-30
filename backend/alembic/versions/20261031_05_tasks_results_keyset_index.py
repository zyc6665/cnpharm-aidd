"""结果中心游标分页：为「终态多值 IN + finished_at keyset」补部分索引。

C1 把 ``/projects/{id}/results`` 改成游标翻页后，排序键是
``(finished_at DESC, id DESC)``，过滤是
``project_id = ? AND status IN ('SUCCESS','FAILURE','CANCELED','TIMEOUT')``。

既有 ``ix_tasks_project_status_finished`` 是
``(project_id, status, finished_at, created_at)``：只能支撑「单终态」（status 等值）
的 seek。默认不带 status 时是 4 个终态的 ``IN (...)``——PostgreSQL 对多值 IN 无法
用「status 在索引键里」的普通复合索引消除 ORDER BY（只能位图/整段扫描后排序，20 万行
真 PG 实测 4.9ms 且退化为 Seq Scan + top-N heapsort）。

因此这里建**部分索引**：把终态集合写进谓词 ``WHERE status IN (...)`，status 就不必
进键；键为 ``(project_id, finished_at DESC NULLS LAST, id DESC)``，一次 Index Only
Scan 即可按全序取页（20 万行真 PG 实测：Index Only Scan、Heap Fetches=0、无 Sort）。

SQLite 不支持 ``NULLS LAST`` 索引语法，建普通升序索引即可（其 DESC 反扫天然把 NULL
放最后，且查询里 ``finished_at IS NOT NULL`` 已排除 NULL）；PG 侧必须显式
``finished_at DESC NULLS LAST``，否则反扫得到 NULLS FIRST 与查询语义不符。

模型 ``Task.__table_args__`` 已同步声明该 ``Index``（含 sqlite/postgresql partial
谓词）；空库经 ``create_all`` 已建同名索引时本迁移会跳过（幂等）。

Revision ID: 20261031_05
Revises: 20261031_04
Create Date: 2026-10-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261031_05"
down_revision = "20261031_04"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_tasks_project_terminal_finished_id"
TABLE = "tasks"
TERMINAL_PREDICATE = "status IN ('SUCCESS','FAILURE','CANCELED','TIMEOUT')"


def _dialect() -> str:
    return op.get_bind().dialect.name


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table: str) -> set[str]:
    if table not in _table_names():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def _column_names(table: str) -> set[str]:
    if table not in _table_names():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if TABLE not in _table_names():
        # 精简基线库可能从未建过 tasks；索引是纯优化，缺表时跳过。
        return
    if {"project_id", "finished_at", "id"} - _column_names(TABLE):
        return
    if INDEX_NAME in _index_names(TABLE):
        return
    if _dialect() == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{INDEX_NAME}" '
                f'ON "{TABLE}" ("project_id", "finished_at" DESC NULLS LAST, "id" DESC) '
                f"WHERE {TERMINAL_PREDICATE}"
            )
        return
    op.create_index(
        INDEX_NAME,
        TABLE,
        ["project_id", "finished_at", "id"],
        sqlite_where=sa.text(TERMINAL_PREDICATE),
    )


def downgrade() -> None:
    if INDEX_NAME not in _index_names(TABLE):
        return
    if _dialect() == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{INDEX_NAME}"')
        return
    op.drop_index(INDEX_NAME, table_name=TABLE)
