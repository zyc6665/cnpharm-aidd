"""Make the Vina screening funnel real and accept CSV / multi-file ligand libraries.

Revision ID: 20261106_01
Revises: 20261105_01

The old Vina package only accepted a multi-record SDF and silently ignored the
screen-page funnel parameters. This migration updates the current Vina tool
version to 1.1.0 with:

* ``pharmacophore_min_features`` — RDKit pharmacophore feature count threshold
* ``docking_score_cutoff`` — best-pose affinity must be <= this value
* ``top_n`` — final kept ligands after ordering by affinity
* ``seed`` — deterministic RDKit embedding + Vina search seed
* optional ``ligand_smiles`` (CSV with SMILES) alongside ``ligand_sdf``
* optional ``binding_pocket`` (PDB used as the docking-box centre)

Downgrade restores the 1.0.0 contract (SDF only, box/exhaustiveness/n_poses).
"""

from __future__ import annotations

import json
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "20261106_01"
down_revision = "20261105_01"
branch_labels = None
depends_on = None

SLUG = "autodock-vina-docking"
OLD_VERSION = "1.0.0"
NEW_VERSION = "1.1.0"
OLD_DIGEST = "sha256:0788db8da9d7b84423cebe5986fceb898b89a0b58b97bd5c10386abfd6c0e50b"
NEW_DIGEST = "sha256:0b56ecb14a17556927bbfdc222366391799729154a1e4c41d9c11a0aa0cf052b"

PROTEIN_INPUT = {
    "name": "protein_pdb",
    "title": "蛋白结构",
    "type": "protein_structure@1",
    "required": True,
    "role_preferences": ["prepared_pdb", "structure_file"],
}
LIGAND_SDF_INPUT = {
    "name": "ligand_sdf",
    "title": "配体 SDF（可多分子批量；与 CSV 二选一）",
    "type": "ligand_structure@1",
    "required": False,
    "role_preferences": ["structure_file"],
}
LIGAND_SMILES_INPUT = {
    "name": "ligand_smiles",
    "title": "配体 SMILES 表（CSV，自动生成 3D；与 SDF 二选一）",
    "type": "molecule_table@1",
    "required": False,
    "role_preferences": ["table_file"],
}
POCKET_INPUT = {
    "name": "binding_pocket",
    "title": "结合口袋（可选，用于确定对接盒中心）",
    "type": "protein_structure@1",
    "required": False,
    "role_preferences": ["prepared_pdb", "structure_file", "raw_structure_file"],
}

OLD_INPUTS = [
    PROTEIN_INPUT,
    {**LIGAND_SDF_INPUT, "required": True, "title": "配体结构（SDF，可多分子批量）"},
]
NEW_INPUTS = [PROTEIN_INPUT, LIGAND_SDF_INPUT, LIGAND_SMILES_INPUT, POCKET_INPUT]

OLD_SCHEMA = {
    "type": "object",
    "properties": {
        "box_size": {
            "type": "number",
            "minimum": 10,
            "maximum": 40,
            "default": 22,
            "description": "立方体对接盒边长（Å），以每个配体的三维质心为中心",
        },
        "exhaustiveness": {
            "type": "integer",
            "minimum": 1,
            "maximum": 32,
            "default": 8,
            "description": "搜索彻底程度，越高越慢越准",
        },
        "n_poses": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "default": 9,
            "description": "每个配体保留的构象数",
        },
        "device": {"type": "string", "enum": ["auto", "cpu"], "default": "cpu"},
    },
    "additionalProperties": False,
}
NEW_SCHEMA = {
    "type": "object",
    "properties": {
        "box_size": {
            "type": "number",
            "minimum": 10,
            "maximum": 40,
            "default": 22,
            "description": "立方体对接盒边长（Å）。提供结合口袋时以口袋中心开盒，否则多配体用蛋白中心、单配体用配体质心。",
        },
        "exhaustiveness": {
            "type": "integer",
            "minimum": 1,
            "maximum": 32,
            "default": 8,
            "description": "Vina 搜索彻底程度，越高越慢越准",
        },
        "n_poses": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "default": 9,
            "description": "每个配体保留的构象数（最终只输出通过筛选的分子）",
        },
        "pharmacophore_min_features": {
            "type": "integer",
            "minimum": 0,
            "maximum": 8,
            "default": 3,
            "description": "对接前药效团特征数下限（氢键供体+氢键受体+芳香中心+疏水中心）",
        },
        "docking_score_cutoff": {
            "type": "number",
            "minimum": -20,
            "maximum": 0,
            "default": -8,
            "description": "对接后最佳打分必须不高于该阈值（kcal/mol，越负越严格）",
        },
        "top_n": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10000,
            "default": 100,
            "description": "通过打分阈值后按打分从好到差保留的分子数",
        },
        "seed": {
            "type": "integer",
            "minimum": 0,
            "maximum": 999999,
            "default": 42,
            "description": "RDKit 3D 构象生成与 Vina 搜索随机种子，保证可复现",
        },
    },
    "additionalProperties": False,
}

NEW_CHANGELOG = "Vina 1.1.0：药效团/打分阈值/top_n/seed 真实生效，支持 SDF、SMILES CSV 与多文件合并上传"
OLD_CHANGELOG = "AutoDock Vina 1.2.7 真实模型包（K8s CPU）"


def _has_tables(bind) -> bool:
    names = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions"}.issubset(names)


def _rewrite(
    bind,
    *,
    version: str,
    inputs: list[dict],
    parameters_schema: dict,
    digest: str,
    changelog: str,
) -> None:
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
    manifest["parameters_schema"] = parameters_schema
    metadata = manifest.setdefault("metadata", {})
    metadata["version"] = version
    metadata["description"] = (
        "AutoDock Vina 分子对接：蛋白结构 + 配体 SDF/SMILES 表，支持药效团、打分阈值与 top_n 真实筛选。"
    )
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
    config["parameters_schema"] = parameters_schema
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
        parameters_schema=NEW_SCHEMA,
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
        parameters_schema=OLD_SCHEMA,
        digest=OLD_DIGEST,
        changelog=OLD_CHANGELOG,
    )
