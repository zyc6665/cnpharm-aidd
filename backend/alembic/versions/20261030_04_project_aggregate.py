"""Task 2：项目聚合根与 RBAC —— ``tasks.project_id`` 真列 + ``projects.version`` 乐观锁。

背景
----
此前任务的「项目归属」只存在 ``tasks.extra_data["project_id"]`` 这个 JSON 字段里：
没有外键约束、无法建索引，项目过滤只能走 ``extra_data["project_id"].as_string()``
这类 JSON 表达式（各数据库方言行为不一致），并且全仓只有 2 个入口会写入它，
于是产生大量「孤儿任务」——有项目上下文却查不出来。

本迁移做三件事：
1. 给 ``tasks`` 加真列 ``project_id``（``String(36) NULL``）+ 索引
   ``ix_tasks_project_id`` + 外键 ``fk_tasks_project_id → projects.id ON DELETE SET NULL``。
   外键用 ``SET NULL`` 而不是 ``CASCADE``：删项目不应连带删掉任务历史，
   但也不该留下指向已删项目的悬空引用。
2. 从旧 ``extra_data`` 回填列值。Postgres 用 ``extra_data::jsonb->>'project_id'``，
   SQLite 用 ``json_extract(extra_data, '$.project_id')``，其余方言跳过。
   回填只写「目标项目确实存在」的行，避免外键在严格方言上失败。
3. 给 ``projects`` 加 ``version INTEGER NOT NULL DEFAULT 1``，作为乐观锁版本号。

幂等
----
所有加列/加索引/加外键都先 ``sa.inspect`` 判断，重复执行安全；表不存在（legacy
恢复场景）直接跳过。``downgrade`` 逆序撤回；SQLite 不支持 ``ALTER TABLE DROP
COLUMN``，删列/删约束走 ``op.batch_alter_table``。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261030_04"
down_revision = "20261029_01"
branch_labels = None
depends_on = None


TASKS = "tasks"
PROJECTS = "projects"
COLUMN = "project_id"
INDEX = "ix_tasks_project_id"
FK = "fk_tasks_project_id"
VERSION = "version"


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _column_names(bind, table: str) -> set[str]:
    if table not in _table_names(bind):
        return set()
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _index_names(bind, table: str) -> set[str]:
    if table not in _table_names(bind):
        return set()
    return {index["name"] for index in sa.inspect(bind).get_indexes(table)}


def _foreign_key_names(bind, table: str) -> set[str]:
    if table not in _table_names(bind):
        return set()
    return {
        fk["name"] for fk in sa.inspect(bind).get_foreign_keys(table) if fk.get("name")
    }


def _backfill_project_ids(bind) -> None:
    """把 ``extra_data["project_id"]`` 回填到真列（按方言取 JSON 值）。"""
    dialect = bind.dialect.name
    if dialect == "postgresql":
        expr = "extra_data::jsonb->>'project_id'"
    elif dialect == "sqlite":
        expr = "json_extract(extra_data, '$.project_id')"
    else:
        return
    bind.execute(
        sa.text(
            f"""
            UPDATE {TASKS}
            SET {COLUMN} = (SELECT p.id FROM {PROJECTS} p WHERE p.id = {expr})
            WHERE {COLUMN} IS NULL
              AND extra_data IS NOT NULL
              AND {expr} IS NOT NULL
              AND EXISTS (SELECT 1 FROM {PROJECTS} p WHERE p.id = {expr})
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    if TASKS not in _table_names(bind):
        # ``tasks`` 由初始基线迁移创建；缺表说明版本链被手工改过，直接跳过。
        return
    tables = _table_names(bind)
    dialect = bind.dialect.name

    if COLUMN not in _column_names(bind, TASKS):
        if dialect == "sqlite" and PROJECTS in tables:
            # SQLite 无法用 ALTER TABLE 追加命名外键（alembic 的 sqlite 方言会抛
            # ``NotImplementedError: No support for ALTER of constraints``）。
            # 用 batch 模式重建表：重建时把命名外键一并带上。
            with op.batch_alter_table(TASKS) as batch_op:
                batch_op.add_column(
                    sa.Column(
                        COLUMN,
                        sa.String(length=36),
                        sa.ForeignKey(
                            f"{PROJECTS}.id", name=FK, ondelete="SET NULL"
                        ),
                        nullable=True,
                    )
                )
        else:
            op.add_column(
                TASKS, sa.Column(COLUMN, sa.String(length=36), nullable=True)
            )

    if (
        PROJECTS in tables
        and dialect != "sqlite"
        and FK not in _foreign_key_names(bind, TASKS)
    ):
        op.create_foreign_key(FK, TASKS, PROJECTS, [COLUMN], ["id"], ondelete="SET NULL")

    if INDEX not in _index_names(bind, TASKS):
        op.create_index(INDEX, TASKS, [COLUMN])

    if PROJECTS in tables and VERSION not in _column_names(bind, PROJECTS):
        op.add_column(
            PROJECTS,
            sa.Column(VERSION, sa.Integer(), nullable=False, server_default="1"),
        )

    if PROJECTS in tables:
        _backfill_project_ids(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if TASKS in _table_names(bind):
        if INDEX in _index_names(bind, TASKS):
            op.drop_index(INDEX, table_name=TASKS)
        has_fk = FK in _foreign_key_names(bind, TASKS)
        has_column = COLUMN in _column_names(bind, TASKS)
        if has_fk or has_column:
            with op.batch_alter_table(TASKS) as batch_op:
                if has_fk:
                    batch_op.drop_constraint(FK, type_="foreignkey")
                if has_column:
                    batch_op.drop_column(COLUMN)

    if PROJECTS in _table_names(bind) and VERSION in _column_names(bind, PROJECTS):
        with op.batch_alter_table(PROJECTS) as batch_op:
            batch_op.drop_column(VERSION)
