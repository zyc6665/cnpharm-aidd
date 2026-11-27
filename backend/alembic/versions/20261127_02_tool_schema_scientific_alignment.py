"""Align Vina docking box center parameter schema with vina_platform.py.

Revision ID: 20261127_02
Revises: 20261127_01
Create Date: 2026-11-27

``autodock-vina-docking``: add optional ``center_x``, ``center_y``, ``center_z``
(Å) to ``parameters_schema`` so direct pocket coordinates pass ``additionalProperties: False``
and align ``box_size`` description with ``vina_platform.py`` (no blind fallback).

Downgrade symmetrically restores the prior ``parameters_schema``.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json

import sqlalchemy as sa
from alembic import op

revision = "20261127_02"
down_revision = "20261127_01"
branch_labels = None
depends_on = None

VINA_SLUG = "autodock-vina-docking"
GROMACS_SLUGS = ("gromacs-md", "gmx-mmpbsa")

VINA_OLD_BOX_DESC = "立方体对接盒边长（Å）。提供结合口袋时以口袋中心开盒，否则多配体用蛋白中心、单配体用配体质心。"
VINA_NEW_BOX_DESC = "立方体对接盒边长（Å）。需提供结合口袋文件或显式中心坐标（center_x/y/z）作为对接中心。"

VINA_CENTER_PROPERTIES = {
    "center_x": {"type": "number", "title": "口袋中心 X (Å)"},
    "center_y": {"type": "number", "title": "口袋中心 Y (Å)"},
    "center_z": {"type": "number", "title": "口袋中心 Z (Å)"},
}

WATER_MODEL_ENUM = ["tip3p", "spc", "tip4p"]
GROMACS_OLD_NSTEPS_MAX = 500000
GROMACS_NEW_NSTEPS_MAX = 5000000
GROMACS_OLD_NSTEPS_DESC = "2 fs/步；默认 2500 步 = 5 ps。"
GROMACS_NEW_NSTEPS_DESC = "2 fs/步；默认 2500 步 = 5 ps（快速测试），正式生产模拟建议 ≥ 500000 步 (1 ns)。"


def _has_tables(bind) -> bool:
    names = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions"}.issubset(names)


def _load_config(raw) -> dict | None:
    if isinstance(raw, dict):
        return copy.deepcopy(raw)
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def patch_vina_schema(schema: object, *, forward: bool) -> bool:
    if not isinstance(schema, dict):
        return False
    props = schema.get("properties")
    if not isinstance(props, dict):
        return False
    changed = False
    if forward:
        for key, spec in VINA_CENTER_PROPERTIES.items():
            if props.get(key) != spec:
                props[key] = dict(spec)
                changed = True
        box = props.get("box_size")
        if isinstance(box, dict) and box.get("description") != VINA_NEW_BOX_DESC:
            box["description"] = VINA_NEW_BOX_DESC
            changed = True
    else:
        for key in VINA_CENTER_PROPERTIES:
            if key in props:
                props.pop(key, None)
                changed = True
        box = props.get("box_size")
        if isinstance(box, dict) and box.get("description") != VINA_OLD_BOX_DESC:
            box["description"] = VINA_OLD_BOX_DESC
            changed = True
    return changed


def patch_gromacs_schema(schema: object, *, forward: bool) -> bool:
    if not isinstance(schema, dict):
        return False
    props = schema.get("properties")
    if not isinstance(props, dict):
        return False
    changed = False
    water = props.get("water_model")
    if isinstance(water, dict):
        if forward:
            if water.get("enum") != WATER_MODEL_ENUM:
                water["enum"] = list(WATER_MODEL_ENUM)
                changed = True
            if "description" not in water:
                water["description"] = "体系使用的水分子模型（tip3p / spc / tip4p）。"
                changed = True
        else:
            if "enum" in water:
                water.pop("enum", None)
                changed = True
            if water.get("description") == "体系使用的水分子模型（tip3p / spc / tip4p）。":
                water.pop("description", None)
                changed = True
    nsteps = props.get("nsteps")
    if isinstance(nsteps, dict):
        if forward:
            if nsteps.get("maximum") != GROMACS_NEW_NSTEPS_MAX:
                nsteps["maximum"] = GROMACS_NEW_NSTEPS_MAX
                changed = True
            if nsteps.get("description") != GROMACS_NEW_NSTEPS_DESC:
                nsteps["description"] = GROMACS_NEW_NSTEPS_DESC
                changed = True
        else:
            if nsteps.get("maximum") != GROMACS_OLD_NSTEPS_MAX:
                nsteps["maximum"] = GROMACS_OLD_NSTEPS_MAX
                changed = True
            if nsteps.get("description") != GROMACS_OLD_NSTEPS_DESC:
                nsteps["description"] = GROMACS_OLD_NSTEPS_DESC
                changed = True
    return changed


def _rewrite_slug(bind, slug: str, patcher, *, forward: bool) -> None:
    row = bind.execute(
        sa.text(
            "SELECT v.id, v.config FROM tools t "
            "JOIN tool_versions v ON v.id = t.current_version_id "
            "WHERE t.slug = :slug"
        ),
        {"slug": slug},
    ).first()
    if not row:
        return

    version_id = str(row[0])
    config = _load_config(row[1])
    if config is None:
        return

    changed = patcher(config.get("parameters_schema"), forward=forward)
    manifest = config.get("tool_package_manifest")
    if isinstance(manifest, dict):
        changed = patcher(manifest.get("parameters_schema"), forward=forward) or changed
    if not changed:
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    config_expr = "CAST(:config AS json)" if bind.dialect.name == "postgresql" else ":config"
    bind.execute(
        sa.text(f"UPDATE tool_versions SET config = {config_expr}, updated_at = :now WHERE id = :id"),
        {"id": version_id, "config": json.dumps(config, ensure_ascii=False), "now": now},
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    _rewrite_slug(bind, VINA_SLUG, patch_vina_schema, forward=True)


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    _rewrite_slug(bind, VINA_SLUG, patch_vina_schema, forward=False)
