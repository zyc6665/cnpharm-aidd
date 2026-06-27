"""workflow contract baseline

Revision ID: 20260624_01
Revises:
Create Date: 2026-06-24 00:00:00
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260624_01"
down_revision = None
branch_labels = None
depends_on = None


def _metadata():
    from app.database.base import Base
    from app.models import agent, files, statistics, system_settings, tasks, tool_capabilities, tools, users, verification, workflows  # noqa: F401

    return Base.metadata


def upgrade() -> None:
    bind = op.get_bind()
    _metadata().create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    _metadata().drop_all(bind=bind, checkfirst=True)
