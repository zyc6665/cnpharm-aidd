"""Switch MSIGN affinity tool to batch ligand input (multi-record SDF).

Revision ID: 20261031_10
Revises: 20261031_09

MSIGN 的模型脚本 ``msign_platform_predict.py`` 本身已支持
``--ligand-sdf``（一个多记录 SDF，逐条配体预测，返回 ``predictions[]`` +
``batch_summary``），镜像内的 ``platform_run.sh`` 也已把 ``ligand_sdf`` 透传
给模型。此前工具包清单只登记了单配体 ``ligand_pdb``，平台侧因此只能逐个跑。

本迁移把 ``msign-affinity-prediction`` 的输入契约改为：

* ``protein_pdb``：``protein_structure@1``（不变）
* ``ligand_sdf``：``ligand_structure@1``，必填——一个 SDF 文件，可含 N 条带
  3D 构象的配体记录；单配体场景即只有一条记录。

输出保持 ``molecule_table@1``（每行一个配体，含 molecule_id 与亲和力/错误）。
镜像 digest 不变（镜像无需重建，批量能力此前已打进镜像）。

Downgrade 把输入还原为原来的 ``protein_pdb + ligand_pdb``（均为
``protein_structure@1``），版本号回退到 1.0.0。
"""

from __future__ import annotations

import json
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "20261031_10"
down_revision = "20261031_09"
branch_labels = None
depends_on = None

SLUG = "msign-affinity-prediction"
NEW_VERSION = "1.1.0"
OLD_VERSION = "1.0.0"

PROTEIN_INPUT = {
    "name": "protein_pdb",
    "title": "蛋白结构",
    "type": "protein_structure@1",
    "required": True,
    "role_preferences": ["prepared_pdb", "structure_file"],
}
LIGAND_SDF_INPUT = {
    "name": "ligand_sdf",
    "title": "配体 SDF（可含多条 3D 记录）",
    "type": "ligand_structure@1",
    "required": True,
    "role_preferences": ["structure_file"],
}
OLD_LIGAND_PDB_INPUT = {
    "name": "ligand_pdb",
    "title": "配体结构（PDB）",
    "type": "protein_structure@1",
    "required": True,
    "role_preferences": ["prepared_pdb", "structure_file"],
}

NEW_CHANGELOG = "MSIGN 支持批量：输入一个多记录 SDF，输出逐配体亲和力表"
OLD_CHANGELOG = "MSIGN 真实模型包（K8s GPU，权重内置）"


def _has_tables(bind) -> bool:
    names = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions"}.issubset(names)


def _rewrite(bind, *, version: str, inputs: list[dict], changelog: str) -> None:
    row = bind.execute(
        sa.text(
            "SELECT t.current_version_id FROM tools t WHERE t.slug = :slug"
        ),
        {"slug": SLUG},
    ).first()
    if not row or not row[0]:
        return
    version_id = str(row[0])
    version_row = bind.execute(
        sa.text("SELECT config FROM tool_versions WHERE id = :id"), {"id": version_id}
    ).first()
    if not version_row:
        return
    raw_config = version_row[0]
    if isinstance(raw_config, dict):
        config = raw_config
    else:
        try:
            config = json.loads(raw_config or "{}")
        except (TypeError, ValueError):
            return
    if not isinstance(config, dict):
        return
    manifest = config.get("tool_package_manifest")
    if isinstance(manifest, dict):
        artifacts = manifest.setdefault("artifacts", {})
        artifacts["inputs"] = inputs
    bind.execute(
        sa.text(
            "UPDATE tool_versions SET version = :version, changelog = :changelog, "
            "config = :config, updated_at = :now WHERE id = :id"
        ),
        {
            "id": version_id,
            "version": version,
            "changelog": changelog,
            "config": json.dumps(config),
            "now": datetime.utcnow(),
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    _rewrite(
        bind,
        version=NEW_VERSION,
        inputs=[PROTEIN_INPUT, LIGAND_SDF_INPUT],
        changelog=NEW_CHANGELOG,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    _rewrite(
        bind,
        version=OLD_VERSION,
        inputs=[PROTEIN_INPUT, OLD_LIGAND_PDB_INPUT],
        changelog=OLD_CHANGELOG,
    )
