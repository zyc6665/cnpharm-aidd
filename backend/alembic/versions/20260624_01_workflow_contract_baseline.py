"""workflow contract baseline

Revision ID: 20260624_01
Revises:
Create Date: 2026-06-24 00:00:00

基线必须完整复现分叉点 `cnpharm-base-ce9a521` 的表结构，否则后续迁移里
指向已删模块的外键在 PostgreSQL 上会直接失败（SQLite 不校验外键目标，
会把问题一路掩盖到生产库）。交付线删掉了 Agent 特性面，`agent_runs` /
`agent_run_steps` 不在当前 metadata 里，但 `20260730_04` 与 `20261025_01`
的 downgrade 都引用了 `agent_runs.id`，因此这两张表**必须在这里建出来**，
再由 `20261025_01` 显式删除。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20260624_01"
down_revision = None
branch_labels = None
depends_on = None


def _metadata():
    from app.database.base import Base
    # 中国医药交付线移除了 Agent 特性面（app/models/agent.py 已删除），
    # 基线不再注册该模块；对应的 8 张表由 20261025_01 显式收敛。
    from app.models import files, statistics, tasks, tool_capabilities, tools, users, verification, workflows  # noqa: F401

    return Base.metadata


def _existing_tables(bind) -> set[str]:
    """当前库里的业务表（排除 alembic 自己的版本表）。"""
    return set(sa.inspect(bind).get_table_names()) - {"alembic_version"}


def _create_retired_agent_tables(bind) -> None:
    """补建分叉点存在、但当前 metadata 已不再声明的 Agent 表。

    只建 `20260730_04` 与 `20261025_01` 会引用到的两张；其余 6 张
    （conversations / conversation_branches / conversation_messages /
    agent_events / plan_versions / plan_decisions）本就由 `20260730_04`
    显式建表。
    """
    existing = set(sa.inspect(bind).get_table_names())

    if "agent_runs" not in existing:
        op.create_table(
            "agent_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), index=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("intent", sa.String(100), nullable=False, index=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending", index=True),
            sa.Column("input_type", sa.String(64), nullable=False),
            sa.Column("input_file_id", sa.String(36), sa.ForeignKey("files.id"), index=True),
            sa.Column("requested_outputs", sa.JSON(), nullable=False),
            sa.Column("plan", sa.JSON(), nullable=False),
            sa.Column("summary", sa.Text()),
            sa.Column("error_message", sa.Text()),
            sa.Column("finished_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if "agent_run_steps" not in existing:
        op.create_table(
            "agent_run_steps",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "agent_run_id",
                sa.String(36),
                sa.ForeignKey("agent_runs.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("step_key", sa.String(100), nullable=False, index=True),
            sa.Column("tool_slug", sa.String(100), nullable=False, index=True),
            sa.Column("tool_id", sa.String(36), sa.ForeignKey("tools.id"), index=True),
            sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), index=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending", index=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("depends_on_step_ids", sa.JSON(), nullable=False),
            sa.Column("semantic_inputs", sa.JSON(), nullable=False),
            sa.Column("semantic_outputs", sa.JSON(), nullable=False),
            sa.Column("params", sa.JSON(), nullable=False),
            sa.Column("input_file_ids", sa.JSON(), nullable=False),
            sa.Column("output_file_ids", sa.JSON(), nullable=False),
            sa.Column("error_message", sa.Text()),
            sa.Column("started_at", sa.DateTime()),
            sa.Column("finished_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def upgrade() -> None:
    bind = op.get_bind()
    _metadata().create_all(bind=bind, checkfirst=True)
    _create_retired_agent_tables(bind)


def downgrade() -> None:
    """回到空库。

    不能用 `_metadata().drop_all()` 收尾。它按**当前** metadata 里的外键图排
    删除顺序，但中间迁移的 downgrade 会重建一些当前模型里已经不存在的表
    （`20260804_01` 重建 `workflow_templates`、`20260729_01` 重建
    `user_sessions`）。这些表不在 metadata 里，drop_all 既不会删它们、也不会
    因为它们的外键而推迟删除 `users`，于是 PostgreSQL 报
    `DependentObjectsStillExistError: cannot drop table users`。SQLite 不校验
    外键目标是否存在，所以这个问题只在 PG 上暴露。

    也不能「逐表 try/except 重试」：PostgreSQL 里一条语句失败会让整个事务进入
    aborted 状态，后续语句一律报 `current transaction is aborted`，重试永远
    不会成功。所以按方言分流：

    * PostgreSQL：`DROP TABLE IF EXISTS ... CASCADE`，由数据库自己处理依赖，
      一次删干净且不会失败；
    * SQLite：不支持 `DROP ... CASCADE`，按当前库里的实际外键关系反复尝试，
      SQLite 在失败后事务仍可继续。
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        for table_name in sorted(_existing_tables(bind)):
            op.execute(sa.text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
        return

    while True:
        remaining = _existing_tables(bind)
        if not remaining:
            break
        progressed = False
        for table_name in sorted(remaining):
            try:
                op.drop_table(table_name)
                progressed = True
            except Exception:  # noqa: BLE001 - 仍被引用，留到下一轮
                continue
        if not progressed:
            raise RuntimeError(
                "downgrade base 无法清空数据库，剩余表存在循环外键: "
                + ", ".join(sorted(remaining))
            )
