"""Add task_input_snapshots and audit_logs.

M7「结果管理与追溯」的存储底座（docs/04 §9.2、§5.4，docs/01 §11.2）。

两张表解决的是同一类问题：**半年后回看一条结果，必须仍能说清它是怎么来的**。

* ``task_input_snapshots`` 记录任务提交那一刻消费的输入（文件 URN、sha256、
  数据版本、语义槽位）。此前这些信息只能从 ``tasks.extra_data`` 与
  ``task_inputs.file_ids`` 反推，而文件可能已被新版本覆盖或软删除，反推出来
  的输入与当年实际运行的不是同一份。
* ``audit_logs`` 此前只以滚动 JSON 文件存在（``app/logging/audit.py``），
  无法被管理台查询（docs/06 P-38），也无法按项目/资源关联，验收条款
  TC-NFR-04 要求六类动作可检索，文件形态无法满足。

两张表都是**只追加**（docs/10 DB-09）：`upgrade` 只建表，`downgrade` 只删表，
任何 UPDATE/DELETE 由 ORM 事件守卫拦截，生产环境再用窄授权兜底。
"""

import sqlalchemy as sa
from alembic import op


revision = "20261026_03"
down_revision = "20261026_02"
branch_labels = None
depends_on = None


TABLE_NAMES = ("task_input_snapshots", "audit_logs")


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    existing = _existing_tables()

    if "task_input_snapshots" not in existing:
        op.create_table(
            "task_input_snapshots",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("task_id", sa.String(length=36), nullable=False),
            sa.Column("input_role", sa.String(length=32), nullable=False),
            sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("entity_type", sa.String(length=64), nullable=True),
            sa.Column("entity_id", sa.String(length=36), nullable=True),
            sa.Column("urn", sa.String(length=512), nullable=True),
            sa.Column("sha256", sa.String(length=64), nullable=True),
            sa.Column("data_version", sa.Integer(), nullable=True),
            sa.Column("file_id", sa.String(length=36), nullable=True),
            sa.Column("detail", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "task_id",
                "input_role",
                "ordinal",
                name="uq_task_input_snapshots_task_role_ordinal",
            ),
        )
        op.create_index(
            "ix_task_input_snapshots_task_id",
            "task_input_snapshots",
            ["task_id"],
        )
        op.create_index(
            "ix_task_input_snapshots_file_id",
            "task_input_snapshots",
            ["file_id"],
        )
        op.create_index(
            "ix_task_input_snapshots_created_at",
            "task_input_snapshots",
            ["created_at"],
        )
        op.create_index(
            "ix_task_input_snapshots_task_role",
            "task_input_snapshots",
            ["task_id", "input_role"],
        )

    if "audit_logs" not in existing:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("actor", sa.String(length=64), nullable=False),
            sa.Column("actor_id", sa.String(length=36), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("result", sa.String(length=16), nullable=False, server_default="success"),
            sa.Column("resource_type", sa.String(length=64), nullable=True),
            sa.Column("resource_id", sa.String(length=64), nullable=True),
            sa.Column("resource_name", sa.String(length=255), nullable=True),
            sa.Column("detail", sa.JSON(), nullable=False),
            sa.Column("ip", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=256), nullable=True),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_audit_logs_actor", "audit_logs", ["actor"])
        op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
        op.create_index("ix_audit_logs_result", "audit_logs", ["result"])
        op.create_index("ix_audit_logs_resource_type", "audit_logs", ["resource_type"])
        op.create_index("ix_audit_logs_resource_id", "audit_logs", ["resource_id"])
        op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])
        op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
        op.create_index(
            "ix_audit_logs_actor_created",
            "audit_logs",
            ["actor", "created_at"],
        )
        op.create_index(
            "ix_audit_logs_resource",
            "audit_logs",
            ["resource_type", "resource_id"],
        )


def downgrade() -> None:
    existing = _existing_tables()
    for table_name in reversed(TABLE_NAMES):
        if table_name in existing:
            op.drop_table(table_name)
