"""Add organizations and research projects.

Revision ID: 20260730_02
Revises: 20260730_01
"""

import sqlalchemy as sa
from alembic import op

revision = "20260730_02"
down_revision = "20260730_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "organizations" not in tables:
        op.create_table(
            "organizations",
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("slug", sa.String(100), nullable=False),
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("slug"),
        )
        op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)
    if "projects" not in tables:
        op.create_table(
            "projects",
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("goal", sa.Text(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("model_policy", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("data_policy", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        for column in ("organization_id", "created_by", "name", "status"):
            op.create_index(f"ix_projects_{column}", "projects", [column])
    if "project_members" not in tables:
        op.create_table(
            "project_members",
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role", sa.String(32), nullable=False),
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        )
        for column in ("project_id", "user_id", "role"):
            op.create_index(f"ix_project_members_{column}", "project_members", [column])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "project_members" in tables:
        op.drop_table("project_members")
    if "projects" in tables:
        op.drop_table("projects")
    if "organizations" in tables:
        op.drop_table("organizations")
