"""Remove the retired guest identity system.

Revision ID: 20260729_01
Revises: 20260728_01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260729_01"
down_revision = "20260728_01"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _drop_column_if_exists(table_name: str, column_name: str, index_name: str | None = None) -> None:
    if table_name not in _table_names() or column_name not in _column_names(table_name):
        return

    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    with op.batch_alter_table(table_name) as batch_op:
        if index_name and index_name in indexes:
            batch_op.drop_index(index_name)
        batch_op.drop_column(column_name)


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if table_name in _table_names() and column.name not in _column_names(table_name):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(column)


def upgrade() -> None:
    bind = op.get_bind()
    if "users" in _table_names():
        bind.execute(sa.text("UPDATE users SET role = 'user' WHERE role = 'guest'"))

    _drop_column_if_exists("tasks", "session_id", "ix_tasks_session_id")
    _drop_column_if_exists("files", "session_id", "ix_files_session_id")
    _drop_column_if_exists("file_access_logs", "session_id")

    if "user_sessions" in _table_names():
        op.drop_table("user_sessions")


def downgrade() -> None:
    _add_column_if_missing("tasks", sa.Column("session_id", sa.String(length=36), nullable=True))
    _add_column_if_missing("files", sa.Column("session_id", sa.String(length=36), nullable=True))
    _add_column_if_missing("file_access_logs", sa.Column("session_id", sa.String(length=36), nullable=True))

    if "tasks" in _table_names() and "ix_tasks_session_id" not in {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("tasks")
    }:
        op.create_index("ix_tasks_session_id", "tasks", ["session_id"])
    if "files" in _table_names() and "ix_files_session_id" not in {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("files")
    }:
        op.create_index("ix_files_session_id", "files", ["session_id"])

    if "user_sessions" not in _table_names():
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=True),
            sa.Column("session_token", sa.String(length=255), nullable=False),
            sa.Column("is_guest", sa.Boolean(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("ip_address", sa.String(length=50), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("session_data", sa.JSON(), nullable=True),
            sa.Column("tasks_today", sa.Integer(), nullable=True),
            sa.Column("last_task_date", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_token"),
        )
        op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
        op.create_index("ix_user_sessions_session_token", "user_sessions", ["session_token"])
