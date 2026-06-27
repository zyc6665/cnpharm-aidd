"""Add tool_capabilities table for AIDD capability registry

Revision ID: 20260627_01
Revises: 20260624_01
Create Date: 2026-06-27 00:00:00
"""

from __future__ import annotations

from alembic import op


revision = "20260627_01"
down_revision = "20260624_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_capabilities (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            tool_id VARCHAR(36),
            capability VARCHAR(100) NOT NULL,
            stage VARCHAR(100) NOT NULL,
            inputs JSON NOT NULL DEFAULT '[]',
            outputs JSON NOT NULL DEFAULT '[]',
            defaults JSON NOT NULL DEFAULT '{}',
            is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            FOREIGN KEY(tool_id) REFERENCES tools (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_tool_capabilities_tool_id "
        "ON tool_capabilities (tool_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tool_capabilities_capability "
        "ON tool_capabilities (capability)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tool_capabilities")
