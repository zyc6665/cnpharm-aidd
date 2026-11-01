"""Task 4-5：工作流节点任务的数据库幂等键。

背景
----
工作流节点建任务原来靠 ``TaskInput.params`` 里的 ``workflow_run_id`` /
``workflow_node_id``，去重只能在「最近 20 条任务」里解析 JSON 猜，存在
「先查后建」的竞态窗口，重复调度会落多条任务。本迁移把这三个归属键落成
``tasks`` 表真列，并加唯一索引，由数据库保证「同一 run + node + attempt
只落一条」。

为什么列名是 ``workflow_run_id``/``workflow_node_id``/``workflow_node_attempt``
----------------------------------------------------------------------------
``run_id``/``node_id`` 在本仓库已有别的语义（``artifacts``/``gpu`` 等），
直接叫 ``run_id`` 会与现有列冲突且含义模糊；``attempt`` 与任务重试的
``execution_attempt_id``（只存在于 ``extra_data``）也不是同一个概念，故加
``workflow_`` 前缀限定在工作流节点调度这一层。

为什么要回填
------------
升级瞬间可能有正在跑的工作流，它们的任务行三列还是 NULL；不回填的话唯一
索引管不住这些在途任务，且 `find_existing_workflow_node_task` 也查不到它们。
同一 ``(run, node)`` 的历史重复行里，优先把键留给**非终态**（pending/queued/
running）中最早的一条，没有非终态行时才留给最早的一条（``attempt=1``），其余
行三列保持 NULL——既不丢数据，也不会让唯一索引建不起来，且不会把键留给一条
已经终态的行导致 lookup 查不到在途任务。

幂等
----
所有加列/建索引先 ``sa.inspect`` 判断，重复执行安全；表不存在直接跳过。
``downgrade`` 逆序撤回；SQLite 删列走 ``op.batch_alter_table``。
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op


revision = "20261030_06"
down_revision = "20261030_05"
branch_labels = None
depends_on = None


TASKS = "tasks"
TASK_INPUTS = "task_inputs"
UNIQUE_INDEX = "uq_tasks_workflow_node_attempt"

NEW_COLUMNS = (
    ("workflow_run_id", sa.String(36), True),
    ("workflow_node_id", sa.String(128), True),
    ("workflow_node_attempt", sa.Integer(), True),
)


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    return {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _index_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _parse_params(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


NON_TERMINAL_STATUSES = {"pending", "queued", "running"}


def _backfill(conn) -> None:
    rows = conn.execute(
        sa.text(
            "SELECT t.id AS task_id, t.status AS status, ti.params AS params "
            f"FROM {TASKS} t JOIN {TASK_INPUTS} ti ON ti.task_id = t.id "
            "ORDER BY t.created_at ASC, t.id ASC"
        )
    ).fetchall()
    groups: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for task_id, status, params in rows:
        payload = _parse_params(params)
        run_id = payload.get("workflow_run_id")
        node_id = payload.get("workflow_node_id")
        if not run_id or not node_id:
            continue
        key = (str(run_id), str(node_id))
        groups.setdefault(key, []).append((str(task_id), str(status or "").lower()))

    for key, candidates in groups.items():
        # 候选按 created_at ASC 排列：优先非终态里最早的一条，否则全部里最早的一条。
        chosen = next(
            (
                task_id
                for task_id, status in candidates
                if status in NON_TERMINAL_STATUSES
            ),
            candidates[0][0],
        )
        conn.execute(
            sa.text(
                f"UPDATE {TASKS} "
                "SET workflow_run_id = :run_id, "
                "workflow_node_id = :node_id, "
                "workflow_node_attempt = 1 "
                "WHERE id = :task_id AND workflow_run_id IS NULL"
            ),
            {"run_id": key[0], "node_id": key[1], "task_id": chosen},
        )


def upgrade() -> None:
    if TASKS not in _table_names():
        return

    existing_columns = _column_names(TASKS)
    for name, column_type, nullable in NEW_COLUMNS:
        if name in existing_columns:
            continue
        op.add_column(TASKS, sa.Column(name, column_type, nullable=nullable))

    if TASK_INPUTS in _table_names():
        _backfill(op.get_bind())

    if UNIQUE_INDEX not in _index_names(TASKS):
        op.create_index(
            UNIQUE_INDEX,
            TASKS,
            ["workflow_run_id", "workflow_node_id", "workflow_node_attempt"],
            unique=True,
        )


def downgrade() -> None:
    if TASKS not in _table_names():
        return

    if UNIQUE_INDEX in _index_names(TASKS):
        op.drop_index(UNIQUE_INDEX, table_name=TASKS)

    existing_columns = _column_names(TASKS)
    to_drop = [name for name, _type, _nullable in NEW_COLUMNS if name in existing_columns]
    if to_drop:
        with op.batch_alter_table(TASKS) as batch_op:
            for name in to_drop:
                batch_op.drop_column(name)
