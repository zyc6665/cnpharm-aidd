"""Add a SMILES-table input to the MSIGN affinity tool (auto 3D conformers).

Revision ID: 20261031_11
Revises: 20261031_10

企业用户常常只有 SMILES 而没有 3D 构象。为了让同一工具既能吃多记录 SDF、
也能吃 SMILES 表，MSIGN 镜像的平台适配层新增 ``smiles_to_sdf.py``：任务启动
时若提供 ``ligand_smiles``（molecule_table@1 的 CSV），先用 RDKit ETKDG 批量
生成 3D 构象并写出多记录 SDF，再交给模型批处理；解析/嵌入失败的分子写入
``artifacts/smiles_conversion_errors.json``，由后处理合并为逐分子 error 行。

输入契约（二选一，运行时强制恰好一个）：

* ``ligand_sdf``：``ligand_structure@1``，现成 3D SDF（可多条记录）
* ``ligand_smiles``：``molecule_table@1``，含 SMILES 列的 CSV（自动生成 3D）

镜像 digest 由 ``sha256:d4e739c7...`` 更新为 ``sha256:babc088f...``（仅重建
MSIGN 镜像，MolP/Pocket2Mol 不动）。版本号 1.1.0 → 1.2.0。

Downgrade 还原 1.1.0 的输入契约与旧镜像 digest。
"""

from __future__ import annotations

import json
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "20261031_11"
down_revision = "20261031_10"
branch_labels = None
depends_on = None

SLUG = "msign-affinity-prediction"
NEW_VERSION = "1.2.0"
OLD_VERSION = "1.1.0"
OLD_DIGEST = "sha256:d4e739c710a85dd5c289e4687f088c72540314886f4161bdb8587532ee8ab4f4"
NEW_DIGEST = "sha256:babc088f46692bf5b4c433bf3a34cb5ea40587351273e449cabf55c91512bca8"

PROTEIN_INPUT = {
    "name": "protein_pdb",
    "title": "蛋白结构",
    "type": "protein_structure@1",
    "required": True,
    "role_preferences": ["prepared_pdb", "structure_file"],
}
LIGAND_SDF_INPUT = {
    "name": "ligand_sdf",
    "title": "配体 SDF（含 3D 构象，可多条记录）",
    "type": "ligand_structure@1",
    "required": False,
    "role_preferences": ["structure_file"],
}
LIGAND_SMILES_INPUT = {
    "name": "ligand_smiles",
    "title": "配体 SMILES 表（自动生成 3D；与 SDF 二选一）",
    "type": "molecule_table@1",
    "required": False,
    "role_preferences": ["table_file"],
}
OLD_INPUTS = [PROTEIN_INPUT, {**LIGAND_SDF_INPUT, "required": True, "title": "配体 SDF（可含多条 3D 记录）"}]
NEW_INPUTS = [PROTEIN_INPUT, LIGAND_SDF_INPUT, LIGAND_SMILES_INPUT]

NEW_CHANGELOG = "MSIGN 支持 SMILES 表输入（自动生成 3D 构象）与多记录 SDF 批量预测"
OLD_CHANGELOG = "MSIGN 支持批量：输入一个多记录 SDF，输出逐配体亲和力表"


def _has_tables(bind) -> bool:
    names = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions"}.issubset(names)


def _rewrite(bind, *, version: str, inputs: list[dict], digest: str, changelog: str) -> None:
    row = bind.execute(
        sa.text("SELECT t.current_version_id FROM tools t WHERE t.slug = :slug"),
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
    raw = version_row[0]
    if isinstance(raw, dict):
        config = raw
    else:
        try:
            config = json.loads(raw or "{}")
        except (TypeError, ValueError):
            return
    if not isinstance(config, dict):
        return
    manifest = config.get("tool_package_manifest")
    if not isinstance(manifest, dict):
        return
    manifest.setdefault("artifacts", {})["inputs"] = inputs
    runtime = manifest.get("runtime")
    if isinstance(runtime, dict):
        artifacts = runtime.get("artifacts")
        if isinstance(artifacts, dict):
            for key in ("primary", "fallback"):
                item = artifacts.get(key)
                if isinstance(item, dict):
                    item["image_digest"] = digest
                    image = item.get("image")
                    if isinstance(image, str) and "@sha256:" in image:
                        item["image"] = image.split("@sha256:", 1)[0] + "@" + digest
    for variant in manifest.get("variants") or []:
        if isinstance(variant, dict):
            if "image_digest" in variant:
                variant["image_digest"] = digest
            image = variant.get("image")
            if isinstance(image, str) and "@sha256:" in image:
                variant["image"] = image.split("@sha256:", 1)[0] + "@" + digest
    image = config.get("image")
    if isinstance(image, str) and "@sha256:" in image:
        config["image"] = image.split("@sha256:", 1)[0] + "@" + digest
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
        inputs=NEW_INPUTS,
        digest=NEW_DIGEST,
        changelog=NEW_CHANGELOG,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    _rewrite(
        bind,
        version=OLD_VERSION,
        inputs=OLD_INPUTS,
        digest=OLD_DIGEST,
        changelog=OLD_CHANGELOG,
    )
