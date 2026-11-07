"""Refresh the Vina 1.1.0 image digest after wiring the runtime parameters.

Revision ID: 20261106_02
Revises: 20261106_01

The first 1.1.0 image only read ``params["params"]`` while the platform sends
``parameters``.  Rebuilt the image with the corrected reader and update the
already seeded tool version in place so existing databases pull the fix.
"""

from __future__ import annotations

import json
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "20261106_02"
down_revision = "20261106_01"
branch_labels = None
depends_on = None

SLUG = "autodock-vina-docking"
NEW_DIGEST = "sha256:0b56ecb14a17556927bbfdc222366391799729154a1e4c41d9c11a0aa0cf052b"


def _replace_image(node, digest: str) -> None:
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key == "image_digest" and isinstance(value, str):
                node[key] = digest
            elif key == "image" and isinstance(value, str) and "@sha256:" in value:
                node[key] = value.split("@sha256:", 1)[0] + "@" + digest
            else:
                _replace_image(value, digest)
    elif isinstance(node, list):
        for item in node:
            _replace_image(item, digest)


def upgrade() -> None:
    bind = op.get_bind()
    names = set(sa.inspect(bind).get_table_names())
    if not {"tools", "tool_versions"}.issubset(names):
        return
    row = bind.execute(
        sa.text("SELECT t.current_version_id FROM tools t WHERE t.slug = :slug"), {"slug": SLUG}
    ).first()
    if not row or not row[0]:
        return
    version_id = str(row[0])
    version_row = bind.execute(
        sa.text("SELECT config FROM tool_versions WHERE id = :id"), {"id": version_id}
    ).first()
    if not version_row:
        return
    raw = version_row[0]
    config = raw if isinstance(raw, dict) else json.loads(raw or "{}")
    if not isinstance(config, dict):
        return
    _replace_image(config, NEW_DIGEST)
    bind.execute(
        sa.text("UPDATE tool_versions SET config = :config, updated_at = :now WHERE id = :id"),
        {"id": version_id, "config": json.dumps(config), "now": datetime.utcnow()},
    )


def downgrade() -> None:
    # The digest is tied to release artefacts, not schema; no-op.
    return
