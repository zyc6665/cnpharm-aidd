"""Pocket2Mol 1.0.2（batch_size 并行采样 + 加载不占显存峰值）与工具时限放宽。

Revision ID: 20261112_01
Revises: 20261110_01

两件事合在一个迁移里，因为它们都是「工具版本的运行契约」：

1. Pocket2Mol 1.0.2：镜像内 runner 支持 ``batch_size``（并行起几路采样进程），
   并把 checkpoint 反序列化改到 CPU 侧（共享卡上直接 ``map_location="cuda"`` 会
   在 ``torch.load`` 阶段就 OOM）。
   上游 ``models/sample.py`` 每个分子都是一个 ``Batch.from_data_list([data])``，
   采样阶段没有 batch 张量，所以「一批生成多少」只能落实为并行进程数。参数名
   取 ``batch_size`` 但按「并行采样批数」解释，避免与训练侧的 batch size 混淆。
2. 时限：原来所有 GPU 模型工具都被种成 60 分钟，导致跑几小时的真实任务一律
   在 3600 秒被 K8s ``activeDeadlineSeconds`` 掐掉（任务 ``ce0c2242…`` 就是
   这样失败的）。这里按工具性质回填 ``tools.timeout_sec`` 与
   ``tool_versions.config`` 里的 ``timeout_sec`` / ``resource_profile.timeout_minutes``。

``TOOL_TIMEOUT_MINUTES`` 与 ``backend/app/services/platform_tool_seeding.py``
里的同名常量必须一致（``test/test_tool_timeout_policy.py`` 会断言），迁移负责
已有库的回填，seeding 负责新库与后续启动期的幂等同步。
"""

from __future__ import annotations

import json
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "20261112_01"
down_revision = "20261110_01"
branch_labels = None
depends_on = None

SLUG = "pocket2mol-pocket-ligand-generation"
NEW_DIGEST = "sha256:82481106504e2f0b3aff3f572293349941f519433217ada5d0d4a8cf10731960"
NEW_VERSION = "1.0.2"
NEW_CHANGELOG = (
    "支持 batch_size（并行采样批数），多批并行采样后合并 SMILES 表与 SDF；"
    "checkpoint 改为先反序列化到 CPU 再搬到设备，避免共享卡上加载即 OOM"
)

DEVICE_SCHEMA = {
    "type": "string",
    "enum": ["auto", "gpu", "cpu"],
    "default": "auto",
    "title": "计算设备",
    "description": "默认 auto：有 GPU 时用 GPU，否则退回 CPU。",
}

BATCH_SIZE_PROPERTY = {
    "type": "integer",
    "minimum": 1,
    "maximum": 8,
    # 默认 2 而不是 4：每路采样进程单独加载一份模型与数据，实测常驻 5~7GB 显存。
    # 24GB 卡上 4 路会把显存吃满（实测两路在已被其他租户占用的卡上就会
    # torch.load 阶段 OOM），所以默认只开两路，独占大卡的用户可以上调。
    "default": 2,
    "title": "并行采样批数",
    "description": (
        "同时起几路采样进程。上游采样是逐分子生成的，这里控制的是并行度，"
        "不是单次前向的分子数；每路约 5~7GB 显存，24GB 卡建议不超过 2 路。"
    ),
}

NEW_SCHEMA = {
    "type": "object",
    "properties": {
        "device": DEVICE_SCHEMA,
        "num_samples": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1000,
            "default": 100,
            "title": "生成数量",
            "description": "本次希望生成的分子数量。",
        },
        "batch_size": BATCH_SIZE_PROPERTY,
        "center_x": {"type": "number", "title": "口袋中心 X"},
        "center_y": {"type": "number", "title": "口袋中心 Y"},
        "center_z": {"type": "number", "title": "口袋中心 Z"},
        "pocket_radius": {
            "type": "number",
            "default": 10.0,
            "title": "口袋半径",
            "description": "以口袋中心为球心的采样半径（Å）。",
        },
    },
    "additionalProperties": False,
}

# slug -> 时限（分钟）。与 platform_tool_seeding.TOOL_TIMEOUT_MINUTES 保持一致。
TOOL_TIMEOUT_MINUTES: dict[str, int] = {
    "pocket2mol-pocket-ligand-generation": 720,
    "gromacs-md": 4320,
    "gmx-mmpbsa": 1440,
    "boltz2-structure-prediction": 360,
    "boltz2-affinity-prediction": 360,
    "lvpocket-pocket-prediction": 240,
    "msign-affinity-prediction": 240,
    "molp-pc-property-prediction": 240,
    "therapainter-peptide-prediction": 240,
    "autodock-vina-docking": 240,
}


def _has_tables(bind) -> bool:
    names = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions"}.issubset(names)


def _load_config(bind, version_id: str) -> dict | None:
    row = bind.execute(
        sa.text("SELECT config FROM tool_versions WHERE id = :id"), {"id": version_id}
    ).first()
    if not row:
        return None
    raw = row[0]
    if isinstance(raw, dict):
        return raw
    try:
        config = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return None
    return config if isinstance(config, dict) else None


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


def _upgrade_pocket2mol(bind, now: datetime) -> None:
    row = bind.execute(
        sa.text("SELECT t.current_version_id FROM tools t WHERE t.slug = :slug"), {"slug": SLUG}
    ).first()
    if not row or not row[0]:
        return
    version_id = str(row[0])
    config = _load_config(bind, version_id)
    if config is None:
        return
    _replace_image(config, NEW_DIGEST)
    config["parameters_schema"] = NEW_SCHEMA
    manifest = config.get("tool_package_manifest")
    if isinstance(manifest, dict):
        manifest["parameters_schema"] = NEW_SCHEMA
    bind.execute(
        sa.text(
            "UPDATE tool_versions SET version = :version, changelog = :changelog, "
            "config = :config, updated_at = :now WHERE id = :id"
        ),
        {
            "id": version_id,
            "version": NEW_VERSION,
            "changelog": NEW_CHANGELOG,
            "config": json.dumps(config),
            "now": now,
        },
    )


def _upgrade_timeouts(bind, now: datetime) -> None:
    for slug, minutes in TOOL_TIMEOUT_MINUTES.items():
        row = bind.execute(
            sa.text("SELECT t.current_version_id FROM tools t WHERE t.slug = :slug"), {"slug": slug}
        ).first()
        if not row:
            continue
        bind.execute(
            sa.text("UPDATE tools SET timeout_sec = :timeout_sec, updated_at = :now WHERE slug = :slug"),
            {"slug": slug, "timeout_sec": minutes * 60, "now": now},
        )
        if not row[0]:
            continue
        version_id = str(row[0])
        config = _load_config(bind, version_id)
        if config is None:
            continue
        config["timeout_sec"] = minutes * 60
        profile = config.get("resource_profile")
        if isinstance(profile, dict):
            profile["timeout_minutes"] = minutes
        bind.execute(
            sa.text("UPDATE tool_versions SET config = :config, updated_at = :now WHERE id = :id"),
            {"id": version_id, "config": json.dumps(config), "now": now},
        )


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    now = datetime.utcnow()
    _upgrade_pocket2mol(bind, now)
    _upgrade_timeouts(bind, now)


def downgrade() -> None:
    # 镜像 digest 与参数契约绑定发布物，时限放宽不回退（回退会把长任务重新掐断）。
    return
