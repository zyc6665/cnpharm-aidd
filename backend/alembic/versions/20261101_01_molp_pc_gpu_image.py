"""把 MolP-PC 工具版本的镜像换成 GPU 版（cu118）

Revision ID: 20261101_01
Revises: 20261031_16
Create Date: 2026-11-01

背景：`compute-molp-pc:1.0.0` 里的 torch 是 CPU 轮子（`2.0.1+cpu`），
在带 GPU 的 Pod 里 `torch.cuda.is_available()` 恒为 False，模型静默退回 CPU 跑
（实测单任务 47 秒，且 Pod 申请了 `nvidia.com/gpu` 却完全没用上）。

`1.1.0` 用同一份模型代码与 platform_adaptor，只把运行环境换成了
`torch==2.0.1+cu118` / `dgl==1.1.2+cu118` / `torch-scatter==2.1.2+pt20cu118`
（配 cuDNN 8.9 + cuBLAS 11.11 的用户态库），实测容器内
`torch.cuda.is_available() == True`、`dgl.graph(...).to("cuda")` 落在 `cuda:0`。

只改工具版本 config 里的镜像引用与 cuda 声明，不动 parameters_schema，
因此不影响已提交任务的参数校验。
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "20261101_01"
down_revision = "20261031_16"
branch_labels = None
depends_on = None

TOOL_SLUG = "molp-pc-property-prediction"
NEW_DIGEST = "sha256:c7e5dfdc8ce1f4669aa00faef71a21a9d61c4ab78449293d9dab81c993a5f516"
OLD_DIGEST = "sha256:e72ee34c4ea8850dcc715dcd43fc0d16c92e3a2643524e1ccac7008551800cc9"
NEW_CUDA = "11.8"
OLD_CUDA = "11.3"


def _rewrite(config: dict, *, digest: str, cuda: str) -> dict:
    image = f"10.202.2.228:30500/aidd/compute-molp-pc@{digest}"
    config = dict(config)
    config["image"] = image

    manifest = config.get("tool_package_manifest")
    if isinstance(manifest, dict):
        manifest = json.loads(json.dumps(manifest))  # 深拷贝，避免原地改到调用方的对象
        runtime = manifest.setdefault("runtime", {})
        runtime["cuda"] = cuda
        artifacts = runtime.setdefault("artifacts", {})
        for slot in ("primary", "fallback"):
            entry = artifacts.get(slot)
            if isinstance(entry, dict):
                entry["image"] = image
                entry["image_digest"] = digest
        for variant in manifest.get("variants", []) or []:
            if isinstance(variant, dict) and variant.get("image"):
                variant["image"] = image
        config["tool_package_manifest"] = manifest
    return config


def _update(*, digest: str, cuda: str) -> None:
    bind = op.get_bind()
    # 本迁移必须能在「从更早版本逐步升级上来的空库/半成品库」上跑通：
    # 那类库里 `tools`/`tool_versions` 可能尚未建出（仓库里有若干用例从
    # 20260730_02 起的局部 schema 一路 upgrade 到 head）。此时本迁移无事可做，
    # 直接返回，绝不能抛「no such table」。
    existing = set(sa.inspect(bind).get_table_names())
    if "tools" not in existing or "tool_versions" not in existing:
        return

    rows = bind.execute(
        sa.text(
            """
            SELECT tv.id, tv.config
            FROM tool_versions tv
            JOIN tools t ON t.id = tv.tool_id
            WHERE t.slug = :slug
            """
        ),
        {"slug": TOOL_SLUG},
    ).fetchall()
    for version_id, config in rows:
        if not isinstance(config, dict):
            continue
        updated = _rewrite(config, digest=digest, cuda=cuda)
        bind.execute(
            sa.text("UPDATE tool_versions SET config = CAST(:config AS json) WHERE id = :id"),
            {"config": json.dumps(updated, ensure_ascii=False), "id": version_id},
        )


def upgrade() -> None:
    _update(digest=NEW_DIGEST, cuda=NEW_CUDA)


def downgrade() -> None:
    _update(digest=OLD_DIGEST, cuda=OLD_CUDA)
