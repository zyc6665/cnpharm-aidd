"""Pocket2Mol 增量适配镜像（adaptor-bd0f0fc0）：补充 RDKit 理化描述符与 Murcko 骨架列。

Revision ID: 20261125_01
Revises: 20261112_01
Create Date: 2026-11-25

PR #159 / Issue #156 在 ``deploy/kubernetes/model-image-template/platform_adaptor/postprocess_result.py``
中补充了 RDKit 描述符与 Murcko 骨架计算，并通过 ``Dockerfile.adaptor`` 提供增量镜像构建。
已在 4090 构建冒烟并推送 ``127.0.0.1:30500/aidd/compute-pocket2mol:adaptor-bd0f0fc0``，
本迁移原地更新 ``pocket2mol-pocket-ligand-generation`` 钉住的镜像 digest。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json

import sqlalchemy as sa
from alembic import op

revision = "20261125_01"
down_revision = "20261112_01"
branch_labels = None
depends_on = None

SLUG = "pocket2mol-pocket-ligand-generation"
OLD_DIGEST = "sha256:82481106504e2f0b3aff3f572293349941f519433217ada5d0d4a8cf10731960"
NEW_DIGEST = "sha256:f11c8c37acb8c37634e6e68d1398fce53c85e378bdb3bbcbf057b0765fe0b2ec"

OLD_CHANGELOG = (
    "支持 batch_size（并行采样批数），多批并行采样后合并 SMILES 表与 SDF；"
    "checkpoint 改为先反序列化到 CPU 再搬到设备，避免共享卡上加载即 OOM"
)
NEW_CHANGELOG = (
    "支持 batch_size（并行采样批数）并叠加适配层 adaptor-bd0f0fc0："
    "后处理补充 9 个 RDKit 理化描述符与 Murcko 骨架列，生成表直接对接类药性筛选面板"
)


def _as_json_text(value) -> str:
    """将数据库取出的 json/text 字段统一转为 JSON 字符串，避免 asyncpg dict repr 报错。"""
    if value is None:
        return "{}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _has_tables(bind) -> bool:
    names = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions"}.issubset(names)


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
    config = _as_json_text(row[1])
    source, target = (OLD_DIGEST, NEW_DIGEST) if forward else (NEW_DIGEST, OLD_DIGEST)
    updated_config = config.replace(source, target)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    config_expr = "CAST(:config AS json)" if bind.dialect.name == "postgresql" else ":config"

    bind.execute(
        sa.text(
            f"UPDATE tool_versions SET config = {config_expr}, "
            "changelog = :changelog, updated_at = :now WHERE id = :id"
        ),
        {
            "id": version_id,
            "config": updated_config,
            "changelog": NEW_CHANGELOG if forward else OLD_CHANGELOG,
            "now": now,
        },
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
