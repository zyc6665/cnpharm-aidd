"""Seed persisted tools for supported AIDD built-in task execution.

Revision ID: 20260728_01
Revises: 20260627_01
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

from app.services.aidd_builtin_tools import _capability_config


revision = "20260728_01"
down_revision = "20260627_01"
branch_labels = None
depends_on = None

BUILTIN_SLUGS = (
    "builtin-sdf-to-smiles-csv",
    "builtin-sdf-to-pdb",
    "builtin-vina-docking",
    "builtin-query-chembl",
    "builtin-query-pubchem",
    "builtin-query-pdbbind",
)


def upgrade() -> None:
    owner_id = os.getenv("AIDD_SYSTEM_USER_ID")
    if not owner_id:
        return

    bind = op.get_bind()
    user_exists = bind.execute(sa.text("SELECT 1 FROM users WHERE id = :id"), {"id": owner_id}).first()
    if not user_exists:
        raise RuntimeError("AIDD_SYSTEM_USER_ID does not reference an existing user")

    now = datetime.utcnow()
    for slug in BUILTIN_SLUGS:
        existing = bind.execute(sa.text("SELECT id FROM tools WHERE slug = :slug"), {"slug": slug}).first()
        if existing:
            continue

        tool_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                """INSERT INTO tools (id, created_at, updated_at, owner_id, name, slug, description,
                category, status, is_public, provider_type, review_status, current_version_id,
                gpu_required, gpu_memory_mb, timeout_sec)
                VALUES (:id, :now, :now, :owner_id, :name, :slug, :description, 'aidd',
                'published', false, 'platform', 'not_required', :version_id, false, 0, 600)"""
            ),
            {
                "id": tool_id,
                "now": now,
                "owner_id": owner_id,
                "name": slug.replace("builtin-", "AIDD ").replace("-", " ").title(),
                "slug": slug,
                "description": "AIDD platform built-in task executor",
                "version_id": version_id,
            },
        )
        bind.execute(
            sa.text(
                """INSERT INTO tool_versions (id, created_at, updated_at, tool_id, version, changelog,
                config, is_active, deprecated) VALUES (:id, :now, :now, :tool_id, '1.0.0',
                'AIDD built-in task executor', :config, true, false)"""
            ),
            {"id": version_id, "now": now, "tool_id": tool_id, "config": json.dumps(_capability_config(slug))},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM tools WHERE slug IN :slugs").bindparams(sa.bindparam("slugs", expanding=True)), {"slugs": BUILTIN_SLUGS})
