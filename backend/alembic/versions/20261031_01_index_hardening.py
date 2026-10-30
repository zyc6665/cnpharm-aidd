"""索引硬化：补齐结果/列表/审计复合索引，清理冗余单列索引

本地 SQLite 合成数据（30,000 tasks / 120,000 audit_logs）实测：

* 结果中心 ``project_id + status IN (...) + ORDER BY finished_at DESC``：
  6.26ms → 1.10ms，计划中的 ``USE TEMP B-TREE FOR ORDER BY`` 消失。
* 任务列表 ``user_id + status + ORDER BY created_at DESC``：3.83ms → 1.03ms，同样
  消掉 TEMP B-TREE。
* 审计 ``action + 时间范围 + ORDER BY created_at DESC``：51.07ms → 0.69ms。

缺的是「等值列 + 排序列」的复合索引，而不是更多单列索引；因此本迁移：

1. 建 13 个复合索引（见 ``NEW_INDEXES`` 与 ``TASKS_FINISHED_DESC``）。
2. 删掉被更长前缀索引 / 唯一约束覆盖的单列冗余索引（见 ``DROP_INDEXES``），
   以及 ``compounds.inchikey`` 上那条与唯一约束同列的非唯一索引。
3. 确保 ``datasets`` 的 ``uq_datasets_project_name_type`` 存在：模型早已声明，
   PostgreSQL 建表迁移从未创建它（SQLite 侧由后续 batch 重建偶然带出）；本迁移
   在 PG 上补建、SQLite 上幂等跳过。
4. ``execution_records`` 补 ``task_id`` 真列并从 ``request_snapshot['task_id']``
   回填，便于按任务反查执行记录。

PostgreSQL 侧建/删索引统一走 ``CREATE/DROP INDEX CONCURRENTLY``（包在
``autocommit_block()`` 里），避免长时间锁表；SQLite 不支持 ``CONCURRENTLY`` 与
``NULLS LAST`` 索引语法，直接普通建删，``ix_tasks_project_status_finished`` 用
普通 ASC（SQLite 的 DESC 扫描天然把 NULL 放最后）。

Revision ID: 20261031_01
Revises: 20261030_07
Create Date: 2026-10-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261031_01"
down_revision = "20261030_07"
branch_labels = None
depends_on = None


TASKS = "tasks"
TASK_LOGS = "task_logs"
ARTIFACTS = "artifacts"
ARTIFACT_VERSIONS = "artifact_versions"
CANDIDATES = "candidates"
CANDIDATE_SETS = "candidate_sets"
FILES = "files"
WORKFLOW_RUNS = "workflow_runs"
TOOLS = "tools"
AUDIT_LOGS = "audit_logs"
DATASETS = "datasets"
EXECUTION_RECORDS = "execution_records"
COMPOUNDS = "compounds"

DATASETS_UNIQUE = "uq_datasets_project_name_type"
DATASETS_UNIQUE_COLUMNS = ["project_id", "name", "dataset_type"]

EXECUTION_TASK_INDEX = "ix_execution_records_task_id"
EXECUTION_TASK_FK = "fk_execution_records_task_id"

#: ``workflow_runs`` 的终态值经 grep 核实（``workflow_reconciliation.py`` /
#: ``workflow_cancellation.py``）：success / failure / canceled；非终态 pending /
#: waiting_task。部分索引只覆盖活跃运行。
WORKFLOW_TERMINAL_PREDICATE = "status NOT IN ('success', 'failure', 'canceled')"
QUEUED_PREDICATE = "status = 'QUEUED'"

#: (索引名, 表, 列, WHERE 谓词或 None)。SQLite 与 PG（非特殊）通用建法。
NEW_INDEXES = [
    ("ix_tasks_project_status_created", TASKS, ["project_id", "status", "created_at"], None),
    ("ix_tasks_user_status_created", TASKS, ["user_id", "status", "created_at"], None),
    ("ix_tasks_status_finished", TASKS, ["status", "finished_at"], None),
    ("ix_tasks_queued_updated", TASKS, ["updated_at"], QUEUED_PREDICATE),
    ("ix_task_logs_task_timestamp", TASK_LOGS, ["task_id", "timestamp"], None),
    ("ix_artifacts_project_type_updated", ARTIFACTS, ["project_id", "artifact_type", "updated_at"], None),
    (
        "ix_artifact_versions_artifact_sha_status",
        ARTIFACT_VERSIONS,
        ["artifact_id", "sha256", "status"],
        None,
    ),
    ("ix_candidates_project_created", CANDIDATES, ["project_id", "created_at"], None),
    ("ix_candidate_sets_project_created", CANDIDATE_SETS, ["project_id", "created_at"], None),
    ("ix_files_owner_created", FILES, ["owner_id", "created_at"], None),
    ("ix_workflow_runs_active_created", WORKFLOW_RUNS, ["created_at"], WORKFLOW_TERMINAL_PREDICATE),
    ("ix_tools_status_created", TOOLS, ["status", "created_at"], None),
]

#: 结果中心排序列：``results.py:209`` 是 ORDER BY finished_at DESC NULLS LAST,
#: created_at DESC。PG 必须显式 DESC NULLS LAST，否则普通 ASC 反扫得到 NULLS FIRST。
TASKS_FINISHED_INDEX = "ix_tasks_project_status_finished"
TASKS_FINISHED_TABLE = TASKS
TASKS_FINISHED_PG_COLUMNS = (
    '"project_id", "status", "finished_at" DESC NULLS LAST, "created_at" DESC'
)
TASKS_FINISHED_SQLITE_COLUMNS = ["project_id", "status", "finished_at", "created_at"]

#: (索引名, 表, 列)。升级时删除、降级时原样建回。
DROP_INDEXES = [
    # 任务/日志/文件/产物：被本迁移新增的复合索引以真前缀覆盖。
    ("ix_tasks_project_id", TASKS, ["project_id"]),
    ("ix_tasks_user_id", TASKS, ["user_id"]),
    ("ix_tasks_status", TASKS, ["status"]),
    ("ix_task_logs_task_id", TASK_LOGS, ["task_id"]),
    ("ix_artifacts_project_id", ARTIFACTS, ["project_id"]),
    ("ix_files_owner_id", FILES, ["owner_id"]),
    ("ix_candidate_sets_project_id", CANDIDATE_SETS, ["project_id"]),
    # 被更长前缀索引 / 唯一约束覆盖的历史单列索引。
    ("ix_project_members_project_id", "project_members", ["project_id"]),
    ("ix_task_input_snapshots_task_id", "task_input_snapshots", ["task_id"]),
    ("ix_artifact_versions_artifact_id", ARTIFACT_VERSIONS, ["artifact_id"]),
    ("ix_artifact_version_files_artifact_version_id", "artifact_version_files", ["artifact_version_id"]),
    ("ix_pockets_structure_id", "pockets", ["structure_id"]),
    ("ix_pocket_residues_pocket_id", "pocket_residues", ["pocket_id"]),
    ("ix_candidates_project_id", CANDIDATES, ["project_id"]),
    ("ix_audit_logs_actor", AUDIT_LOGS, ["actor"]),
    ("ix_audit_logs_actor_id", AUDIT_LOGS, ["actor_id"]),
    ("ix_audit_logs_resource_type", AUDIT_LOGS, ["resource_type"]),
    ("ix_audit_logs_result", AUDIT_LOGS, ["result"]),
    ("ix_upload_sessions_idempotency_key", "upload_sessions", ["idempotency_key"]),
    ("ix_compounds_inchikey", COMPOUNDS, ["inchikey"]),
]


def _dialect() -> str:
    return op.get_bind().dialect.name


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table: str) -> set[str]:
    if table not in _table_names():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def _unique_names(table: str) -> set[str]:
    if table not in _table_names():
        return set()
    return {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints(table)
        if constraint.get("name")
    }


def _column_names(table: str) -> set[str]:
    if table not in _table_names():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _create_index(name: str, table: str, columns: list[str], where: str | None) -> None:
    if table not in _table_names():
        # 历史手工 DDL 的基线库可能从未建过该表（正常库由基线 create_all 建出）。
        # 索引是纯优化，缺表时跳过，避免迁移在精简基线库上失败。
        return
    if set(columns) - _column_names(table):
        # 同理：手工构造的 legacy ``tasks`` 没有 ``finished_at`` 等列时跳过。
        return
    if name in _index_names(table):
        return
    if _dialect() == "postgresql":
        column_sql = ", ".join(f'"{column}"' for column in columns)
        statement = (
            f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{name}" '
            f'ON "{table}" ({column_sql})'
        )
        if where:
            statement += f" WHERE {where}"
        with op.get_context().autocommit_block():
            op.execute(statement)
        return
    keyword: dict[str, object] = {}
    if where:
        keyword["sqlite_where"] = sa.text(where)
    op.create_index(name, table, columns, **keyword)


def _drop_index(name: str, table: str) -> None:
    if name not in _index_names(table):
        return
    if _dialect() == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"')
        return
    op.drop_index(name, table_name=table)


def _create_tasks_finished_index() -> None:
    name = TASKS_FINISHED_INDEX
    table = TASKS_FINISHED_TABLE
    if table not in _table_names():
        return
    if {"project_id", "status", "finished_at", "created_at"} - _column_names(table):
        return
    if name in _index_names(table):
        return
    if _dialect() == "postgresql":
        statement = (
            f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{name}" '
            f'ON "{table}" ({TASKS_FINISHED_PG_COLUMNS})'
        )
        with op.get_context().autocommit_block():
            op.execute(statement)
        return
    op.create_index(name, table, TASKS_FINISHED_SQLITE_COLUMNS)


def _add_datasets_unique() -> None:
    if DATASETS not in _table_names():
        return
    if DATASETS_UNIQUE in _unique_names(DATASETS) or DATASETS_UNIQUE in _index_names(DATASETS):
        return
    if _dialect() == "postgresql":
        op.create_unique_constraint(DATASETS_UNIQUE, DATASETS, DATASETS_UNIQUE_COLUMNS)
        return
    # SQLite 不能 ALTER TABLE ADD CONSTRAINT；唯一索引等价地保证「项目内同名同类型唯一」。
    op.create_index(DATASETS_UNIQUE, DATASETS, DATASETS_UNIQUE_COLUMNS, unique=True)


def _drop_datasets_unique() -> None:
    if _dialect() == "postgresql" and DATASETS_UNIQUE in _unique_names(DATASETS):
        op.drop_constraint(DATASETS_UNIQUE, DATASETS, type_="unique")
        return
    if DATASETS_UNIQUE in _index_names(DATASETS):
        _drop_index(DATASETS_UNIQUE, DATASETS)


def _backfill_execution_task_id() -> None:
    if "task_id" not in _column_names(EXECUTION_RECORDS):
        return
    if TASKS not in _table_names():
        # legacy 精简基线库可能没有 ``tasks``（``test_alembic_migration_dry_run``
        # 会在中途 revision 建库后直接 upgrade head）。没有 tasks 就没有可校验的
        # 目标行，也就没有可回填的合法值，跳过即可。
        return
    if _dialect() == "postgresql":
        # ``?`` 是 **jsonb** 的运算符，``json`` 上没有它（报
        # ``operator does not exist: json ? unknown``）。``request_snapshot`` 是
        # ``sa.JSON`` → PG 上是 ``json``，所以必须先转 jsonb。
        op.execute(
            "UPDATE execution_records SET task_id = request_snapshot->>'task_id' "
            "WHERE task_id IS NULL AND (request_snapshot::jsonb) ? 'task_id' "
            "AND EXISTS (SELECT 1 FROM tasks t WHERE t.id = request_snapshot->>'task_id')"
        )
        return
    op.execute(
        "UPDATE execution_records SET task_id = json_extract(request_snapshot, '$.task_id') "
        "WHERE task_id IS NULL "
        "AND json_extract(request_snapshot, '$.task_id') IS NOT NULL "
        "AND json_extract(request_snapshot, '$.task_id') IN (SELECT id FROM tasks)"
    )


def _add_execution_task_column() -> None:
    if EXECUTION_RECORDS not in _table_names():
        return
    if "task_id" in _column_names(EXECUTION_RECORDS):
        return
    op.add_column(
        EXECUTION_RECORDS,
        sa.Column("task_id", sa.String(length=36), nullable=True),
    )
    if _dialect() == "postgresql" and TASKS in _table_names():
        op.create_foreign_key(
            EXECUTION_TASK_FK,
            EXECUTION_RECORDS,
            TASKS,
            ["task_id"],
            ["id"],
            ondelete="SET NULL",
        )


def _foreign_key_names(table: str) -> set[str]:
    if table not in _table_names():
        return set()
    return {
        fk["name"]
        for fk in sa.inspect(op.get_bind()).get_foreign_keys(table)
        if fk.get("name")
    }


def _drop_execution_task_column() -> None:
    if "task_id" not in _column_names(EXECUTION_RECORDS):
        return
    if _dialect() == "postgresql":
        if EXECUTION_TASK_FK in _foreign_key_names(EXECUTION_RECORDS):
            op.drop_constraint(EXECUTION_TASK_FK, EXECUTION_RECORDS, type_="foreignkey")
        op.drop_column(EXECUTION_RECORDS, "task_id")
        return
    # SQLite 的 ALTER TABLE DROP COLUMN 遇到外键引用该列会报
    # "unknown column ... in foreign key definition"（3.35 的限制），走 batch 重建。
    with op.batch_alter_table(EXECUTION_RECORDS, recreate="always") as batch:
        batch.drop_column("task_id")


def upgrade() -> None:
    for name, table, columns, where in NEW_INDEXES:
        _create_index(name, table, columns, where)
    _create_tasks_finished_index()

    for name, table, _columns in DROP_INDEXES:
        _drop_index(name, table)

    _add_datasets_unique()

    _add_execution_task_column()
    if EXECUTION_TASK_INDEX in _index_names(EXECUTION_RECORDS):
        pass
    else:
        _create_index(EXECUTION_TASK_INDEX, EXECUTION_RECORDS, ["task_id"], None)
    _backfill_execution_task_id()


def downgrade() -> None:
    _drop_index(EXECUTION_TASK_INDEX, EXECUTION_RECORDS)
    _drop_execution_task_column()

    _drop_datasets_unique()

    # 先删本迁移新增的索引，再把被删的历史索引建回，回到升级前状态。
    _drop_index(TASKS_FINISHED_INDEX, TASKS_FINISHED_TABLE)
    for name, table, _columns, _where in NEW_INDEXES:
        _drop_index(name, table)

    for name, table, columns in DROP_INDEXES:
        _create_index(name, table, columns, None)
