"""移除 Pocket2Mol 契约中未生效的 pocket_radius 参数（#172）。

Revision ID: 20261125_02
Revises: 20261125_01
Create Date: 2026-11-25

Pocket2Mol 容器入口脚本仅读取 ``bbox_size``（默认 23.0 Å），从未读取 ``pocket_radius``。
本迁移原地清理 ``pocket2mol-pocket-ligand-generation`` 参数契约里的 ``pocket_radius``，
并在 ``downgrade()`` 中对称恢复该字段。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json

import sqlalchemy as sa
from alembic import op

revision = "20261125_02"
down_revision = "20261125_01"
branch_labels = None
depends_on = None

SLUG = "pocket2mol-pocket-ligand-generation"

POCKET_RADIUS_PROPERTY = {
    "type": "number",
    "default": 10.0,
    "title": "口袋半径",
    "description": "以口袋中心为球心的采样半径（Å）。",
}

NEW_SCHEMA = {
    "type": "object",
    "properties": {
        "device": {
            "type": "string",
            "enum": ["auto", "gpu", "cpu"],
            "default": "auto",
            "title": "计算设备",
            "description": "默认 auto：有 GPU 时用 GPU，否则退回 CPU。",
        },
        "num_samples": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1000,
            "default": 100,
            "title": "生成数量",
            "description": "本次希望生成的分子数量。",
        },
        "batch_size": {
            "type": "integer",
            "minimum": 1,
            "maximum": 8,
            "default": 2,
            "title": "并行采样批数",
            "description": (
                "同时起几路采样进程。上游采样是逐分子生成的，这里控制的是并行度，"
                "不是单次前向的分子数；每路约 5~7GB 显存，24GB 卡建议不超过 2 路。"
            ),
        },
        "center_x": {"type": "number", "title": "口袋中心 X"},
        "center_y": {"type": "number", "title": "口袋中心 Y"},
        "center_z": {"type": "number", "title": "口袋中心 Z"},
    },
    "additionalProperties": False,
}


def _has_tables(bind) -> bool:
    names = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions"}.issubset(names)


def _load_config(raw) -> dict | None:
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _patch_schema(schema: object, *, forward: bool) -> bool:
    if not isinstance(schema, dict):
        return False
    props = schema.get("properties")
    if not isinstance(props, dict):
        return False
    if forward:
        if "pocket_radius" not in props:
            return False
        props.pop("pocket_radius", None)
        return True
    if "pocket_radius" in props:
        return False
    props["pocket_radius"] = dict(POCKET_RADIUS_PROPERTY)
    return True


def _rewrite(bind, *, forward: bool) -> None:
    row = bind.execute(
        sa.text(
            "SELECT v.id, v.config FROM tools t "
            "JOIN tool_versions v ON v.id = t.current_version_id "
            "WHERE t.slug = :slug"
        ),
        {"slug": SLUG},
    ).first()
    if not row:
        return

    version_id = str(row[0])
    config = _load_config(row[1])
    if config is None:
        return

    changed = _patch_schema(config.get("parameters_schema"), forward=forward)
    manifest = config.get("tool_package_manifest")
    if isinstance(manifest, dict):
        changed = _patch_schema(manifest.get("parameters_schema"), forward=forward) or changed
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
    _rewrite(bind, forward=True)


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    _rewrite(bind, forward=False)
