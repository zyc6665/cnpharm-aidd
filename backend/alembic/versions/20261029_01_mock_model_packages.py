"""Register demo mock model packages for remaining pages.

Revision ID: 20261029_01
Revises: 20261028_08

The six packages under ``example/mock-models/<slug>/`` are demonstration-only
Tool Package v2 manifests (``metadata.mock: true``). This migration registers
each package as a ``tools`` row plus ``tool_versions.config['tool_package_manifest']``
and a matching ``tool_capabilities`` row so the whole chain (manifest -> task ->
result) can be exercised without any real model runtime. Downgrade removes
exactly the rows it created.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op


revision = "20261029_01"
down_revision = "20261028_08"
branch_labels = None
depends_on = None


MOCK_PACKAGE_SLUGS = (
    "std-diff-molecule-generation",
    "therapainter-peptide-design",
    "admet-prediction",
    "vina-virtual-screening",
    "gromacs-md-simulation",
    "gmx-mmpbsa-free-energy",
)

PACKAGE_CATEGORY = "mock-model"
PACKAGE_PROVIDER = "platform"
PACKAGE_VERSION = "0.1.0"
PACKAGE_TIMEOUT_SEC = 600


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_seed_target_tables(bind):
        return

    owner_id = _resolve_owner_id(bind)
    if owner_id is None:
        # No user exists yet; nothing to attach the demo tools to.
        return

    now = datetime.utcnow()
    for slug in MOCK_PACKAGE_SLUGS:
        manifest = _load_manifest(slug)
        if manifest is None:
            continue
        tool_id = _ensure_mock_tool(bind, now, owner_id=owner_id, slug=slug, manifest=manifest)
        _ensure_mock_capability(bind, now, tool_id=tool_id, slug=slug, manifest=manifest)


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_seed_target_tables(bind):
        return

    for slug in MOCK_PACKAGE_SLUGS:
        row = bind.execute(
            sa.text("SELECT id FROM tools WHERE slug = :slug"), {"slug": slug}
        ).first()
        if not row:
            continue
        tool_id = str(row[0])
        bind.execute(
            sa.text("DELETE FROM tool_capabilities WHERE tool_id = :tool_id"),
            {"tool_id": tool_id},
        )
        bind.execute(
            sa.text("UPDATE tools SET current_version_id = NULL WHERE id = :tool_id"),
            {"tool_id": tool_id},
        )
        bind.execute(
            sa.text("DELETE FROM tool_versions WHERE tool_id = :tool_id"),
            {"tool_id": tool_id},
        )
        bind.execute(
            sa.text("DELETE FROM tools WHERE id = :tool_id"), {"tool_id": tool_id}
        )


def _load_manifest(slug: str) -> dict[str, Any] | None:
    package_dir = (
        Path(__file__).resolve().parents[3] / "example" / "mock-models" / slug
    )
    if not (package_dir / "tool.yaml").is_file():
        return None
    from app.tool_packages.loader import ToolPackageLoadError, load_tool_package

    try:
        manifest = load_tool_package(package_dir)
    except ToolPackageLoadError:
        return None
    # Inline variant files into the persisted manifest so runtime manifest parsing
    # (app.tool_packages.config_resolver) sees fully-resolved variant dicts.
    return manifest.model_dump(mode="json")


def _mock_config(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "python_script",
        "script_path": "runner/mock_runner.py",
        "timeout_sec": PACKAGE_TIMEOUT_SEC,
        "agent_access": True,
        "mock": True,
        "tool_package_manifest": manifest,
    }


def _ensure_mock_tool(
    bind,
    now: datetime,
    *,
    owner_id: str,
    slug: str,
    manifest: dict[str, Any],
) -> str:
    metadata = manifest.get("metadata") or {}
    name = str(metadata.get("name") or slug)
    description = metadata.get("description")
    config = json.dumps(_mock_config(manifest))

    row = bind.execute(
        sa.text("SELECT id, current_version_id FROM tools WHERE slug = :slug"),
        {"slug": slug},
    ).first()
    if row:
        tool_id = str(row[0])
        version_id = str(row[1]) if row[1] else str(uuid.uuid4())
        bind.execute(
            sa.text(
                "UPDATE tools SET owner_id = :owner_id, name = :name, description = :description, "
                "category = :category, status = 'published', is_public = true, "
                "provider_type = :provider, review_status = 'not_required', "
                "current_version_id = :version_id, gpu_required = false, gpu_memory_mb = 0, "
                "timeout_sec = :timeout_sec, updated_at = :now WHERE id = :tool_id"
            ),
            {
                "owner_id": owner_id,
                "name": name,
                "description": description,
                "category": PACKAGE_CATEGORY,
                "provider": PACKAGE_PROVIDER,
                "version_id": version_id,
                "timeout_sec": PACKAGE_TIMEOUT_SEC,
                "now": now,
                "tool_id": tool_id,
            },
        )
    else:
        tool_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO tools (id, created_at, updated_at, owner_id, name, slug, description, "
                "category, status, is_public, provider_type, review_status, current_version_id, "
                "gpu_required, gpu_memory_mb, timeout_sec) "
                "VALUES (:id, :now, :now, :owner_id, :name, :slug, :description, "
                ":category, 'published', true, :provider, 'not_required', :version_id, "
                "false, 0, :timeout_sec)"
            ),
            {
                "id": tool_id,
                "now": now,
                "owner_id": owner_id,
                "name": name,
                "slug": slug,
                "description": description,
                "category": PACKAGE_CATEGORY,
                "provider": PACKAGE_PROVIDER,
                "version_id": version_id,
                "timeout_sec": PACKAGE_TIMEOUT_SEC,
            },
        )

    version_exists = bind.execute(
        sa.text("SELECT 1 FROM tool_versions WHERE id = :id"), {"id": version_id}
    ).first()
    if version_exists:
        bind.execute(
            sa.text(
                "UPDATE tool_versions SET version = :version, changelog = :changelog, "
                "config = :config, is_active = true, deprecated = false, updated_at = :now "
                "WHERE id = :id"
            ),
            {
                "id": version_id,
                "version": PACKAGE_VERSION,
                "changelog": "Demo mock model package (Tool Package v2)",
                "config": config,
                "now": now,
            },
        )
    else:
        bind.execute(
            sa.text(
                "INSERT INTO tool_versions (id, created_at, updated_at, tool_id, version, "
                "changelog, config, is_active, deprecated) VALUES (:id, :now, :now, :tool_id, "
                ":version, :changelog, :config, true, false)"
            ),
            {
                "id": version_id,
                "now": now,
                "tool_id": tool_id,
                "version": PACKAGE_VERSION,
                "changelog": "Demo mock model package (Tool Package v2)",
                "config": config,
            },
        )
    return tool_id


def _capability_payload(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    artifacts = manifest.get("artifacts") or {}
    inputs = []
    for item in artifacts.get("inputs") or []:
        if not isinstance(item, dict) or not item.get("type"):
            continue
        inputs.append(
            {
                "semantic_type": str(item["type"]),
                "field": str(item.get("name") or item["type"]),
                "required": bool(item.get("required", True)),
                "accepted_extensions": [],
            }
        )
    outputs = []
    for item in artifacts.get("outputs") or []:
        if not isinstance(item, dict) or not item.get("type"):
            continue
        outputs.append(
            {
                "semantic_type": str(item["type"]),
                "source": "artifact",
                "match": {"content_type": str(item["type"])},
                "path": str(item.get("name") or item["type"]),
                "required": bool(item.get("required", True)),
            }
        )
    return inputs, outputs


def _ensure_mock_capability(
    bind,
    now: datetime,
    *,
    tool_id: str,
    slug: str,
    manifest: dict[str, Any],
) -> None:
    inputs, outputs = _capability_payload(manifest)
    if not inputs or not outputs:
        return
    capability = str((manifest.get("metadata") or {}).get("slug") or slug)
    stage = capability
    payload = {
        "tool_id": tool_id,
        "capability": capability,
        "stage": stage,
        "inputs": json.dumps(inputs),
        "outputs": json.dumps(outputs),
        "defaults": json.dumps({}),
        "now": now,
    }
    row = bind.execute(
        sa.text("SELECT id FROM tool_capabilities WHERE tool_id = :tool_id"),
        {"tool_id": tool_id},
    ).first()
    if row:
        bind.execute(
            sa.text(
                "UPDATE tool_capabilities SET capability = :capability, stage = :stage, "
                "inputs = :inputs, outputs = :outputs, defaults = :defaults, "
                "is_builtin = false, is_enabled = true, updated_at = :now WHERE id = :id"
            ),
            {**payload, "id": row[0]},
        )
        return
    bind.execute(
        sa.text(
            "INSERT INTO tool_capabilities (id, created_at, updated_at, tool_id, capability, "
            "stage, inputs, outputs, defaults, is_builtin, is_enabled) "
            "VALUES (:id, :now, :now, :tool_id, :capability, :stage, :inputs, :outputs, "
            ":defaults, false, true)"
        ),
        {**payload, "id": str(uuid.uuid4())},
    )


def _has_seed_target_tables(bind) -> bool:
    tables = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions", "tool_capabilities"}.issubset(tables)


def _resolve_owner_id(bind) -> str | None:
    row = bind.execute(
        sa.text(
            "SELECT id FROM users WHERE role = 'admin' AND status = 'active' "
            "ORDER BY created_at ASC LIMIT 1"
        )
    ).first()
    if row:
        return str(row[0])
    row = bind.execute(
        sa.text("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")
    ).first()
    return str(row[0]) if row else None
