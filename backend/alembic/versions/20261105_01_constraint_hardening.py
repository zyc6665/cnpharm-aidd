"""约束硬化：溯源列补外键 + 用户名/LDAP/工作流项目索引双真源收敛。

背景
----
1. **溯源列无外键**：``task_input_snapshots.task_id`` /
   ``artifact_versions.source_task_id`` / ``artifacts.source_task_id`` 此前只是裸
   字符串。删任务后溯源行静默悬挂（实测 ``task_input_snapshots`` 悬挂 100/136、
   ``artifact_versions`` 悬挂 21、``artifacts`` 悬挂 3），追溯包指向不存在的执行。
   本迁移补真实外键，语义：
   - ``task_input_snapshots.task_id`` → ``tasks.id`` **ON DELETE CASCADE**：
     快照是任务的从属物，任务没了快照即无意义；该表只追加，不会误删业务数据。
   - ``artifact_versions.source_task_id`` / ``artifacts.source_task_id`` →
     ``tasks.id`` **ON DELETE SET NULL**：产物是独立资产，删任务不得带走产物，
     溯源退化为未知但数据完整。
2. **索引双真源**：``uq_users_username_lower`` / ``uq_users_ldap_dn`` 此前只在
   ``20261031_07`` 的原生 SQL 里建、模型未声明；``ix_workflow_runs_project_id``
   库上存在但模型未声明。模型补齐声明后（见 app/models/users.py、workflows.py），
   本迁移幂等确保这些索引在库上存在，使 ``alembic check`` 不再漂移。

清障（开发期）
--------------
加外键前必须先清理会挡路的脏数据（脏数据会直接让 ADD CONSTRAINT 失败）。
本迁移在 upgrade() 起始执行：

    DELETE FROM task_input_snapshots WHERE task_id NOT IN (SELECT id FROM tasks)
    UPDATE artifact_versions SET source_task_id = NULL WHERE source_task_id NOT IN (SELECT id FROM tasks)
    UPDATE artifacts          SET source_task_id = NULL WHERE source_task_id NOT IN (SELECT id FROM tasks)

**这是开发期重建前的清障，生产环境应先审计再决定**（生产一般应先把悬挂来源
人工归位或留档，而不是直接删/置空）。用户已明确同意本仓库当前为模拟数据、
可重建，故此处直接清除。

幂等性
------
- 全新库由基线 ``20260624_01`` 的 ``Base.metadata.create_all()`` 按当前模型建出
  全部表、外键与索引，本迁移检测到已存在即跳过（不会重复建，不会触发重建表）。
- 存量库（外键/索引缺失）才会真正执行 DDL。
- SQLite 加/删外键必须整表重建（``batch_alter_table(..., recreate="always")``）；
  PostgreSQL 直接 ``ALTER TABLE ADD/DROP CONSTRAINT``。

downgrade 逆序移除本迁移负责的外键与索引。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261105_01"
down_revision = "20261104_01"
branch_labels = None
depends_on = None


SNAPSHOTS = "task_input_snapshots"
VERSIONS = "artifact_versions"
ARTIFACTS = "artifacts"
TASKS = "tasks"
USERS = "users"
WORKFLOW_RUNS = "workflow_runs"

USERNAME_INDEX = "uq_users_username_lower"
LDAP_DN_INDEX = "uq_users_ldap_dn"
WORKFLOW_PROJECT_INDEX = "ix_workflow_runs_project_id"

#: (表, 外键列, 目标表, 目标列, ondelete, 约束名)
FK_SPECS = (
    (SNAPSHOTS, "task_id", TASKS, "id", "CASCADE", "fk_task_input_snapshots_task_id"),
    (VERSIONS, "source_task_id", TASKS, "id", "SET NULL", "fk_artifact_versions_source_task_id"),
    (ARTIFACTS, "source_task_id", TASKS, "id", "SET NULL", "fk_artifacts_source_task_id"),
)


# --------------------------------------------------------------------------- #
# 元数据探测（不 import 应用模型，纯 SQL / op）
# --------------------------------------------------------------------------- #
def _bind():
    return op.get_bind()


def _dialect() -> str:
    return _bind().dialect.name


def _table_names() -> set[str]:
    return set(sa.inspect(_bind()).get_table_names())


def _column_names(table: str, known_tables: set[str] | None = None) -> set[str]:
    tables = _table_names() if known_tables is None else known_tables
    if table not in tables:
        return set()
    return {column["name"] for column in sa.inspect(_bind()).get_columns(table)}


def _index_names(table: str) -> set[str]:
    if table not in _table_names():
        return set()
    return {
        index["name"]
        for index in sa.inspect(_bind()).get_indexes(table)
        if index.get("name")
    }


def _fk_on(table: str, columns: list[str], referred_table: str) -> dict | None:
    """返回指向 ``referred_table`` 且受约束列完全匹配的外键（忽略约束名）。

    必须忽略名字：SQLite 由 ``create_all`` 建的外键是匿名的（name=None），
    PostgreSQL 由 ``create_all`` 建的外键是 ``<table>_<col>_fkey`` 形式，都与我们
    显式起的 ``fk_*`` 不同。按结构匹配才能做到「已存在则跳过」。
    """
    if table not in _table_names():
        return None
    for fk in sa.inspect(_bind()).get_foreign_keys(table):
        if (fk.get("constrained_columns") or []) == list(columns) and fk.get(
            "referred_table"
        ) == referred_table:
            return fk
    return None


# --------------------------------------------------------------------------- #
# upgrade
# --------------------------------------------------------------------------- #
def _cleanup_dangling() -> None:
    tables = _table_names()
    if TASKS not in tables:
        return
    if SNAPSHOTS in tables:
        op.execute(
            sa.text(
                f"DELETE FROM {SNAPSHOTS} "
                f"WHERE task_id NOT IN (SELECT id FROM {TASKS})"
            )
        )
    for table in (VERSIONS, ARTIFACTS):
        if table in tables and "source_task_id" in _column_names(table, tables):
            op.execute(
                sa.text(
                    f"UPDATE {table} SET source_task_id = NULL "
                    f"WHERE source_task_id IS NOT NULL "
                    f"AND source_task_id NOT IN (SELECT id FROM {TASKS})"
                )
            )


def _add_foreign_keys() -> None:
    tables = _table_names()
    dialect = _dialect()
    for table, column, referred, referred_col, ondelete, name in FK_SPECS:
        if table not in tables or referred not in tables:
            continue
        if column not in _column_names(table, tables):
            continue
        if _fk_on(table, [column], referred) is not None:
            continue  # 全新库 create_all 已带外键
        if dialect == "sqlite":
            with op.batch_alter_table(table, recreate="always") as batch:
                batch.create_foreign_key(name, referred, [column], [referred_col], ondelete=ondelete)
        else:
            op.create_foreign_key(name, table, referred, [column], [referred_col], ondelete=ondelete)


def _ensure_indexes() -> None:
    dialect = _dialect()
    if USERS in _table_names():
        existing = _index_names(USERS)
        if USERNAME_INDEX not in existing:
            # 两方言都支持表达式索引；与模型 Index(func.lower(username)) 对齐。
            op.execute(
                sa.text(
                    f'CREATE UNIQUE INDEX "{USERNAME_INDEX}" ON "{USERS}" (lower(username))'
                )
            )
        if LDAP_DN_INDEX not in existing:
            op.execute(
                sa.text(
                    f'CREATE UNIQUE INDEX "{LDAP_DN_INDEX}" ON "{USERS}" (ldap_dn) '
                    f"WHERE ldap_dn IS NOT NULL"
                )
            )
    if WORKFLOW_RUNS in _table_names():
        if WORKFLOW_PROJECT_INDEX not in _index_names(WORKFLOW_RUNS):
            # 与模型 Index("ix_workflow_runs_project_id", "project_id") 对齐。
            op.create_index(WORKFLOW_PROJECT_INDEX, WORKFLOW_RUNS, ["project_id"])


def upgrade() -> None:
    _cleanup_dangling()
    _add_foreign_keys()
    _ensure_indexes()


# --------------------------------------------------------------------------- #
# downgrade
# --------------------------------------------------------------------------- #
def _drop_foreign_keys() -> None:
    tables = _table_names()
    dialect = _dialect()
    for table, column, referred, _referred_col, _ondelete, _name in FK_SPECS:
        if table not in tables:
            continue
        fk = _fk_on(table, [column], referred)
        if fk is None:
            continue
        constraint_name = fk.get("name")
        if dialect == "sqlite":
            # SQLite 无法按名删除匿名外键；整表重建需要约束名。全新库由基线
            # create_all 建的外键是匿名的，这里跳过——最终 downgrade 到 base 时
            # 基线 drop_all 会删除整表连带外键。存量具名外键才尝试删除。
            if not constraint_name:
                continue
            with op.batch_alter_table(table, recreate="always") as batch:
                batch.drop_constraint(constraint_name, type_="foreignkey")
        else:
            op.drop_constraint(constraint_name, table, type_="foreignkey")


def _drop_indexes() -> None:
    if USERS in _table_names():
        existing = _index_names(USERS)
        for name in (USERNAME_INDEX, LDAP_DN_INDEX):
            if name in existing:
                op.drop_index(name, table_name=USERS)
    if WORKFLOW_RUNS in _table_names() and WORKFLOW_PROJECT_INDEX in _index_names(WORKFLOW_RUNS):
        op.drop_index(WORKFLOW_PROJECT_INDEX, table_name=WORKFLOW_RUNS)


def downgrade() -> None:
    _drop_foreign_keys()
    _drop_indexes()
