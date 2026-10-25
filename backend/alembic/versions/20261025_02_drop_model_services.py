"""Drop the LLM model service configuration table.

The China Pharmaceutical delivery line is an offline, in-network deployment:
the platform must not hold any outbound LLM endpoint, API key, or telemetry
configuration.  Agent planning/approval was removed in ``20261025_01``; that
left ``model_services`` without a consumer, because the only remaining reader
was the admin settings page for OpenAI-compatible providers.

``downgrade`` re-creates the schema only (no data).
"""

import sqlalchemy as sa
from alembic import op


revision = "20261025_02"
down_revision = "20261025_01"
branch_labels = None
depends_on = None


TABLE_NAME = "model_services"


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    if TABLE_NAME in _existing_tables():
        op.drop_table(TABLE_NAME)


def downgrade() -> None:
    if TABLE_NAME in _existing_tables():
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "provider_type",
            sa.String(50),
            nullable=False,
            server_default="openai_compatible",
        ),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("api_key_encrypted", sa.Text()),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false(), index=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true(), index=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="2048"),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.2"),
        sa.Column("last_test_status", sa.String(32)),
        sa.Column("last_test_message", sa.Text()),
        sa.Column("last_tested_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
