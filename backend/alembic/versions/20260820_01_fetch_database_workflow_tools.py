"""Expose external database fetch built-ins in the workflow workbench.

Revision ID: 20260820_01
Revises: 20260804_02
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

from app.services.aidd_builtin_tools import _capability_config


revision = "20260820_01"
down_revision = "20260804_02"
branch_labels = None
depends_on = None


GROUP = {
    "name": "数据获取",
    "slug": "data-acquisition",
    "description": "从外部科学数据库获取蛋白和配体结构",
    "sort_order": 0,
}

TOOLS = (
    {
        "slug": "builtin-fetch-pdb",
        "name": "Fetch PDB Structure",
        "description": "Fetch a protein structure from RCSB PDB by PDB ID and emit protein_structure@1.",
        "sort_order": 1,
    },
    {
        "slug": "builtin-fetch-ligand",
        "name": "Fetch PubChem Ligand",
        "description": "Fetch 2D/3D ligand SDF files from PubChem by CID and emit ligand_structure@1.",
        "sort_order": 2,
    },
)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_seed_target_tables(bind):
        return

    owner_id = _resolve_owner_id(bind)
    if not owner_id:
        return

    now = datetime.utcnow()
    group_id = _ensure_workbench_group(bind, now)
    for item in TOOLS:
        tool_id = _ensure_builtin_tool(bind, now, owner_id=owner_id, item=item)
        _ensure_group_mapping(bind, now, group_id=group_id, tool_id=tool_id, sort_order=item["sort_order"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_seed_target_tables(bind):
        return

    slugs = [item["slug"] for item in TOOLS]
    tool_ids = [
        row[0]
        for row in bind.execute(
            sa.text("SELECT id FROM tools WHERE slug IN :slugs").bindparams(
                sa.bindparam("slugs", expanding=True)
            ),
            {"slugs": slugs},
        ).fetchall()
    ]
    if tool_ids:
        bind.execute(
            sa.text("DELETE FROM tool_workbench_group_mappings WHERE tool_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": tool_ids},
        )
    bind.execute(
        sa.text("DELETE FROM tools WHERE slug IN :slugs").bindparams(
            sa.bindparam("slugs", expanding=True)
        ),
        {"slugs": slugs},
    )
    bind.execute(
        sa.text(
            "DELETE FROM tool_workbench_groups WHERE slug = :slug "
            "AND NOT EXISTS (SELECT 1 FROM tool_workbench_group_mappings WHERE group_id = tool_workbench_groups.id)"
        ),
        {"slug": GROUP["slug"]},
    )


def _has_seed_target_tables(bind) -> bool:
    tables = set(sa.inspect(bind).get_table_names())
    return {
        "tools",
        "tool_versions",
        "tool_workbench_groups",
        "tool_workbench_group_mappings",
    }.issubset(tables)


def _resolve_owner_id(bind) -> str | None:
    configured = os.getenv("AIDD_SYSTEM_USER_ID")
    if configured:
        row = bind.execute(sa.text("SELECT id FROM users WHERE id = :id"), {"id": configured}).first()
        if row:
            return str(row[0])

    row = bind.execute(
        sa.text(
            "SELECT id FROM users WHERE role = 'admin' AND status = 'active' "
            "ORDER BY created_at ASC LIMIT 1"
        )
    ).first()
    if row:
        return str(row[0])

    row = bind.execute(sa.text("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")).first()
    return str(row[0]) if row else None


def _ensure_workbench_group(bind, now: datetime) -> str:
    row = bind.execute(
        sa.text("SELECT id FROM tool_workbench_groups WHERE slug = :slug"),
        {"slug": GROUP["slug"]},
    ).first()
    if row:
        bind.execute(
            sa.text(
                "UPDATE tool_workbench_groups SET name = :name, description = :description, "
                "sort_order = :sort_order, is_enabled = true, updated_at = :now WHERE id = :id"
            ),
            {**GROUP, "id": row[0], "now": now},
        )
        return str(row[0])

    group_id = str(uuid.uuid4())
    bind.execute(
        sa.text(
            "INSERT INTO tool_workbench_groups "
            "(id, created_at, updated_at, name, slug, description, sort_order, is_enabled) "
            "VALUES (:id, :now, :now, :name, :slug, :description, :sort_order, true)"
        ),
        {**GROUP, "id": group_id, "now": now},
    )
    return group_id


def _ensure_builtin_tool(bind, now: datetime, *, owner_id: str, item: dict[str, object]) -> str:
    slug = str(item["slug"])
    config = json.dumps(_capability_config(slug))
    row = bind.execute(sa.text("SELECT id, current_version_id FROM tools WHERE slug = :slug"), {"slug": slug}).first()
    if row:
        tool_id = str(row[0])
        version_id = str(row[1]) if row[1] else str(uuid.uuid4())
        bind.execute(
            sa.text(
                "UPDATE tools SET owner_id = :owner_id, name = :name, description = :description, "
                "category = 'data-acquisition', status = 'published', is_public = true, "
                "provider_type = 'platform', review_status = 'not_required', current_version_id = :version_id, "
                "gpu_required = false, gpu_memory_mb = 0, timeout_sec = 120, updated_at = :now WHERE id = :tool_id"
            ),
            {
                "owner_id": owner_id,
                "name": item["name"],
                "description": item["description"],
                "version_id": version_id,
                "now": now,
                "tool_id": tool_id,
            },
        )
        version_exists = bind.execute(
            sa.text("SELECT 1 FROM tool_versions WHERE id = :id"), {"id": version_id}
        ).first()
        if version_exists:
            bind.execute(
                sa.text(
                    "UPDATE tool_versions SET version = '1.0.0', changelog = :changelog, "
                    "config = :config, is_active = true, deprecated = false, updated_at = :now WHERE id = :id"
                ),
                {
                    "id": version_id,
                    "now": now,
                    "config": config,
                    "changelog": "Workflow external database fetch built-in",
                },
            )
        else:
            _insert_tool_version(bind, now, version_id=version_id, tool_id=tool_id, config=config)
        return tool_id

    tool_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    bind.execute(
        sa.text(
            "INSERT INTO tools (id, created_at, updated_at, owner_id, name, slug, description, "
            "category, status, is_public, provider_type, review_status, current_version_id, "
            "gpu_required, gpu_memory_mb, timeout_sec) "
            "VALUES (:id, :now, :now, :owner_id, :name, :slug, :description, 'data-acquisition', "
            "'published', true, 'platform', 'not_required', :version_id, false, 0, 120)"
        ),
        {
            "id": tool_id,
            "now": now,
            "owner_id": owner_id,
            "name": item["name"],
            "slug": slug,
            "description": item["description"],
            "version_id": version_id,
        },
    )
    _insert_tool_version(bind, now, version_id=version_id, tool_id=tool_id, config=config)
    return tool_id


def _insert_tool_version(bind, now: datetime, *, version_id: str, tool_id: str, config: str) -> None:
    bind.execute(
        sa.text(
            "INSERT INTO tool_versions (id, created_at, updated_at, tool_id, version, changelog, "
            "config, is_active, deprecated) VALUES (:id, :now, :now, :tool_id, '1.0.0', "
            ":changelog, :config, true, false)"
        ),
        {
            "id": version_id,
            "now": now,
            "tool_id": tool_id,
            "config": config,
            "changelog": "Workflow external database fetch built-in",
        },
    )


def _ensure_group_mapping(bind, now: datetime, *, group_id: str, tool_id: str, sort_order: int) -> None:
    row = bind.execute(
        sa.text(
            "SELECT id FROM tool_workbench_group_mappings "
            "WHERE group_id = :group_id AND tool_id = :tool_id"
        ),
        {"group_id": group_id, "tool_id": tool_id},
    ).first()
    if row:
        bind.execute(
            sa.text(
                "UPDATE tool_workbench_group_mappings SET sort_order = :sort_order, "
                "is_recommended = true, is_enabled = true, updated_at = :now WHERE id = :id"
            ),
            {"id": row[0], "sort_order": sort_order, "now": now},
        )
        return

    bind.execute(
        sa.text(
            "INSERT INTO tool_workbench_group_mappings "
            "(id, created_at, updated_at, tool_id, group_id, sort_order, is_recommended, is_enabled) "
            "VALUES (:id, :now, :now, :tool_id, :group_id, :sort_order, true, true)"
        ),
        {
            "id": str(uuid.uuid4()),
            "now": now,
            "tool_id": tool_id,
            "group_id": group_id,
            "sort_order": sort_order,
        },
    )
