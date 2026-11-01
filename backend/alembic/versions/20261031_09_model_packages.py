"""Register three real model packages: MolP-PC, MSIGN and Pocket2Mol.

Revision ID: 20261031_09
Revises: 20261031_08

与 LVpocket 迁移同构：``k8s_job`` + 容器镜像 + 标准 ToolPackage v2 清单。
三个模型的镜像由 ``deploy/model-images/k8s/`` 下的 Dockerfile 构建，模型权重
随镜像分发（``model.tar.gz``），因此 ``runtime.weights`` 为空。

镜像内容：
- compute-molp-pc：分子性质预测（RDKit + PyTorch），输入 SMILES 表，输出性质表。
- compute-msign：蛋白-配体亲和力预测，输入蛋白/配体结构，输出亲和力表。
- compute-pocket2mol：口袋条件分子生成，输入口袋蛋白结构，输出分子表 + 配体 SDF。

Downgrade 只删本迁移创建的三个工具，不动其它行。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "20261031_09"
down_revision = "20261031_08"
branch_labels = None
depends_on = None

REGISTRY = "10.202.2.228:30500"
TIMEOUT_SEC = 3600

DEVICE_SCHEMA = {"type": "string", "enum": ["auto", "gpu", "cpu"], "default": "auto"}


def _molecule_table_input(name: str, title: str) -> dict:
    return {
        "name": name,
        "title": title,
        "type": "molecule_table@1",
        "required": True,
        "role_preferences": ["table_file"],
    }


def _protein_input(name: str = "protein_pdb") -> dict:
    return {
        "name": name,
        "title": "蛋白结构",
        "type": "protein_structure@1",
        "required": True,
        "role_preferences": ["prepared_pdb", "structure_file"],
    }


def _ligand_input(name: str = "ligand_pdb") -> dict:
    return {
        "name": name,
        "title": "配体结构（PDB）",
        "type": "protein_structure@1",
        "required": True,
        "role_preferences": ["prepared_pdb", "structure_file"],
    }


def _model(
    *,
    slug: str,
    name: str,
    description: str,
    version: str,
    image_name: str,
    image_digest: str,
    inputs: list[dict],
    outputs: list[dict],
    parameters_schema: dict,
    gpu_memory_mb: int,
    python: str,
    cuda: str,
    includes: list[str],
    changelog: str,
) -> dict:
    image = f"{REGISTRY}/aidd/{image_name}@{image_digest}"
    manifest = {
        "api_version": "aidd.sciminer/tool-package",
        "kind": "ToolPackage",
        "metadata": {"slug": slug, "name": name, "version": version, "description": description},
        "artifacts": {"inputs": inputs, "outputs": outputs},
        "parameters_schema": parameters_schema,
        "runtime": {
            "python": python,
            "cuda": cuda,
            "executor_support": ["k8s_job"],
            "selection_policy": "按 GPU 显存与加速器类型选择具备 nvidia GPU 的 k8s 节点",
            "weights": {"manifest_uri": "", "manifest_sha256": "", "mounts": []},
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": image,
                    "image_digest": image_digest,
                    "includes": includes,
                },
                "fallback": {
                    "kind": "container",
                    "image": image,
                    "image_digest": image_digest,
                    "includes": ["python"],
                },
            },
            "cache_policy": {
                "key_fields": [
                    "metadata.slug",
                    "metadata.version",
                    "runtime.artifacts.primary.image_digest",
                ],
                "mutable_host_paths_forbidden": True,
            },
        },
        "variants": [
            {
                "name": "nvidia-cuda",
                "accelerator": "nvidia_cuda",
                "executor_types": ["container"],
                "image": image,
                "entrypoint": [
                    "/usr/bin/tini",
                    "--",
                    "/opt/sciminer/platform_adaptor/entrypoint.sh",
                ],
                "validation_status": "validated",
                "hardware_validated": False,
            }
        ],
    }
    config = {
        "type": "k8s_job",
        "tool_package_manifest": manifest,
        "image": image,
        "timeout_sec": TIMEOUT_SEC,
        "gpu_required": True,
        "gpu_memory_required_mb": gpu_memory_mb,
        "parameters_schema": parameters_schema,
        "runtime": {},
    }
    return {
        "slug": slug,
        "name": name,
        "description": description,
        "version": version,
        "changelog": changelog,
        "config": config,
        "gpu_memory_mb": gpu_memory_mb,
    }


MODELS = [
    _model(
        slug="molp-pc-property-prediction",
        name="MolP-PC 分子性质预测",
        description="基于 MolP-PC 的分子理化性质/ADMET 预测，输入 SMILES 表，输出逐分子性质表。",
        version="1.0.0",
        image_name="compute-molp-pc",
        image_digest="sha256:e72ee34c4ea8850dcc715dcd43fc0d16c92e3a2643524e1ccac7008551800cc9",
        inputs=[_molecule_table_input("smiles_csv", "分子 SMILES 表")],
        outputs=[
            {"name": "properties", "type": "molecule_table@1", "cardinality": "one", "required": True},
            {"name": "report", "type": "run_report@1", "cardinality": "one", "required": False},
        ],
        parameters_schema={
            "type": "object",
            "properties": {"device": DEVICE_SCHEMA},
            "additionalProperties": False,
        },
        gpu_memory_mb=4096,
        python="3.8",
        cuda="11.3",
        includes=["python", "torch", "rdkit"],
        changelog="MolP-PC 真实模型包（K8s GPU，权重内置）",
    ),
    _model(
        slug="msign-affinity-prediction",
        name="MSIGN 蛋白-配体亲和力预测",
        description="基于 MSIGN 的蛋白-配体结合亲和力预测，输入蛋白与配体结构，输出亲和力表。",
        version="1.0.0",
        image_name="compute-msign",
        image_digest="sha256:d4e739c710a85dd5c289e4687f088c72540314886f4161bdb8587532ee8ab4f4",
        inputs=[_protein_input(), _ligand_input()],
        outputs=[
            {"name": "affinity", "type": "molecule_table@1", "cardinality": "one", "required": True},
            {"name": "report", "type": "run_report@1", "cardinality": "one", "required": False},
        ],
        parameters_schema={
            "type": "object",
            "properties": {"device": DEVICE_SCHEMA},
            "additionalProperties": False,
        },
        gpu_memory_mb=8192,
        python="3.8",
        cuda="11.3",
        includes=["python", "torch"],
        changelog="MSIGN 真实模型包（K8s GPU，权重内置）",
    ),
    _model(
        slug="pocket2mol-pocket-ligand-generation",
        name="Pocket2Mol 口袋分子生成",
        description="基于 Pocket2Mol 的口袋条件分子生成，输入口袋蛋白结构，输出生成分子表与配体 SDF。",
        version="1.0.0",
        image_name="compute-pocket2mol",
        image_digest="sha256:f834fd01c614c531d861d55a32b2b60454575b12a3a04f861dc69d859a72dd26",
        inputs=[_protein_input()],
        outputs=[
            {"name": "molecules", "type": "molecule_table@1", "cardinality": "one", "required": True},
            {"name": "ligands", "type": "ligand_structure@1", "cardinality": "one", "required": True},
            {"name": "report", "type": "run_report@1", "cardinality": "one", "required": False},
        ],
        parameters_schema={
            "type": "object",
            "properties": {
                "device": DEVICE_SCHEMA,
                "num_samples": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
                "center_x": {"type": "number"},
                "center_y": {"type": "number"},
                "center_z": {"type": "number"},
                "pocket_radius": {"type": "number", "default": 10.0},
            },
            "additionalProperties": False,
        },
        gpu_memory_mb=8192,
        python="3.8",
        cuda="11.3",
        includes=["python", "torch", "rdkit"],
        changelog="Pocket2Mol 真实模型包（K8s GPU，权重内置）",
    ),
]


def _resolve_owner_id(bind) -> str | None:
    row = bind.execute(
        sa.text("SELECT id FROM users WHERE role = 'admin' ORDER BY created_at ASC LIMIT 1")
    ).first()
    if row:
        return str(row[0])
    row = bind.execute(sa.text("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")).first()
    return str(row[0]) if row else None


def _has_tables(bind) -> bool:
    names = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions", "users"}.issubset(names)


def _upsert(bind, model: dict, owner_id: str, now: datetime) -> None:
    slug = model["slug"]
    row = bind.execute(
        sa.text("SELECT id, current_version_id FROM tools WHERE slug = :slug"), {"slug": slug}
    ).first()
    version_id = str(row[1]) if row and row[1] else str(uuid.uuid4())
    config = json.dumps(model["config"])

    if row:
        tool_id = str(row[0])
        bind.execute(
            sa.text(
                "UPDATE tools SET owner_id = :owner_id, name = :name, description = :description, "
                "category = 'model', status = 'published', is_public = true, "
                "provider_type = 'platform', review_status = 'not_required', "
                "current_version_id = :version_id, gpu_required = true, gpu_memory_mb = :gpu_memory_mb, "
                "timeout_sec = :timeout_sec, updated_at = :now WHERE id = :tool_id"
            ),
            {
                "owner_id": owner_id,
                "name": model["name"],
                "description": model["description"],
                "version_id": version_id,
                "gpu_memory_mb": model["gpu_memory_mb"],
                "timeout_sec": TIMEOUT_SEC,
                "now": now,
                "tool_id": tool_id,
            },
        )
    else:
        tool_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO tools (id, created_at, updated_at, owner_id, name, slug, description, "
                "category, status, is_public, provider_type, review_status, current_version_id, "
                "gpu_required, gpu_memory_mb, timeout_sec) "
                "VALUES (:id, :now, :now, :owner_id, :name, :slug, :description, "
                "'model', 'published', true, 'platform', 'not_required', :version_id, "
                "true, :gpu_memory_mb, :timeout_sec)"
            ),
            {
                "id": tool_id,
                "now": now,
                "owner_id": owner_id,
                "name": model["name"],
                "slug": slug,
                "description": model["description"],
                "version_id": version_id,
                "gpu_memory_mb": model["gpu_memory_mb"],
                "timeout_sec": TIMEOUT_SEC,
            },
        )

    exists = bind.execute(
        sa.text("SELECT 1 FROM tool_versions WHERE id = :id"), {"id": version_id}
    ).first()
    if exists:
        bind.execute(
            sa.text(
                "UPDATE tool_versions SET version = :version, changelog = :changelog, config = :config, "
                "is_active = true, deprecated = false, updated_at = :now WHERE id = :id"
            ),
            {
                "id": version_id,
                "version": model["version"],
                "changelog": model["changelog"],
                "config": config,
                "now": now,
            },
        )
    else:
        bind.execute(
            sa.text(
                "INSERT INTO tool_versions (id, created_at, updated_at, tool_id, version, changelog, "
                "config, is_active, deprecated) VALUES (:id, :now, :now, :tool_id, :version, "
                ":changelog, :config, true, false)"
            ),
            {
                "id": version_id,
                "now": now,
                "tool_id": tool_id,
                "version": model["version"],
                "changelog": model["changelog"],
                "config": config,
            },
        )


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    owner_id = _resolve_owner_id(bind)
    if owner_id is None:
        return
    now = datetime.utcnow()
    for model in MODELS:
        _upsert(bind, model, owner_id, now)


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    for model in MODELS:
        row = bind.execute(
            sa.text("SELECT id FROM tools WHERE slug = :slug"), {"slug": model["slug"]}
        ).first()
        if not row:
            continue
        tool_id = str(row[0])
        bind.execute(
            sa.text("DELETE FROM tool_capabilities WHERE tool_id = :tool_id"), {"tool_id": tool_id}
        )
        bind.execute(
            sa.text("UPDATE tools SET current_version_id = NULL WHERE id = :tool_id"),
            {"tool_id": tool_id},
        )
        bind.execute(
            sa.text("DELETE FROM tool_versions WHERE tool_id = :tool_id"), {"tool_id": tool_id}
        )
        bind.execute(sa.text("DELETE FROM tools WHERE id = :tool_id"), {"tool_id": tool_id})
