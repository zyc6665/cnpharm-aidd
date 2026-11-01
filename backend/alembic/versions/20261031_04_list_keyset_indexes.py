"""补齐结果中心 / 产物 / 工作流运行三张列表的游标（keyset）分页索引。

C1 子任务把三个列表改成「游标翻页」——从上一页最后一行的位置继续：
``(sort_col, id) < (:last_ts, :last_id) ORDER BY sort_col DESC, id DESC``。这类查询
需要「等值前缀列 + 排序键」复合索引才能做索引区间 seek；缺索引时会退化成整段扫描
（游标白上，见 docs/20 §5.13 与 20261031_03 的实测）。

本迁移只补索引，不动数据。三张索引分别支撑：

* ``artifacts (project_id, created_at, id)``
  → ``list_artifacts`` 无 metadata_* 过滤时的 SQL keyset：
    ``WHERE project_id = ? AND (created_at, id) < (?, ?) ORDER BY created_at DESC, id DESC``。
    用 created_at 而非 updated_at，因为 updated_at 非只增，深页会漏/重。
* ``workflow_runs (project_id, created_at, id)``
  → ``list_workflow_runs`` 按项目：``WHERE project_id = ? AND (created_at, id) < (?, ?)``。
* ``workflow_runs (owner_id, created_at, id)``
  → ``list_workflow_runs`` 按 owner（无 project 作用域）：
    ``WHERE owner_id = ? AND (created_at, id) < (?, ?)``。

（末列 ``id`` 不能省：排序键是 ``(created_at DESC, id DESC)``，只到 ``created_at``
时 SQLite 仍会对同一毫秒的并列行做「RIGHT PART OF ORDER BY」内存排序。）

模型 ``Artifact.__table_args__`` / ``WorkflowRun.__table_args__`` 已同步声明这些
``Index(...)``（模型是索引单一真源）。因此空库经基线 ``create_all`` 已建好同名索引，
本迁移的 ``_create_index`` 见索引已存在会跳过（幂等）。

PostgreSQL 侧统一用 ``CONCURRENTLY``（包在 ``autocommit_block()`` 里）避免锁表；
SQLite 没有 ``CONCURRENTLY``，普通 ``op.create_index`` 即可。

Revision ID: 20261031_04
Revises: 20261031_03
Create Date: 2026-10-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261031_04"
down_revision = "20261031_03"
branch_labels = None
depends_on = None

ARTIFACTS = "artifacts"
WORKFLOW_RUNS = "workflow_runs"

#: (索引名, 表名, 列, 支撑的查询)。升级建、降级删。
NEW_INDEXES = [
    (
        "ix_artifacts_project_created_id",
        ARTIFACTS,
        ["project_id", "created_at", "id"],
        "产物列表游标：project_id + (created_at, id) keyset",
    ),
    (
        "ix_workflow_runs_project_created",
        WORKFLOW_RUNS,
        ["project_id", "created_at", "id"],
        "工作流运行游标（按项目）：project_id + (created_at, id) keyset",
    ),
    (
        "ix_workflow_runs_owner_created",
        WORKFLOW_RUNS,
        ["owner_id", "created_at", "id"],
        "工作流运行游标（按 owner）：owner_id + (created_at, id) keyset",
    ),
]


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


def _create_index(name: str, table: str, columns: list[str]) -> None:
    if table not in _table_names():
        # 精简基线库可能从未建过该表；索引是纯优化，缺表时跳过。
        return
    if set(columns) - _column_names(table):
        # legacy 手工 DDL 表可能缺列，跳过以免迁移失败。
        return
    if name in _index_names(table):
        return
    if _dialect() == "postgresql":
        column_sql = ", ".join(f'"{column}"' for column in columns)
        with op.get_context().autocommit_block():
            op.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{name}" '
                f'ON "{table}" ({column_sql})'
            )
        return
    op.create_index(name, table, columns)


def _drop_index(name: str, table: str) -> None:
    if name not in _index_names(table):
        return
    if _dialect() == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"')
        return
    op.drop_index(name, table_name=table)


def upgrade() -> None:
    for name, table, columns, _purpose in NEW_INDEXES:
        _create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns, _purpose in NEW_INDEXES:
        _drop_index(name, table)
