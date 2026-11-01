"""Register AutoDock Vina docking tool package.

Revision ID: 20261031_12
Revises: 20261031_11

AutoDock Vina 1.2.7 分子对接（CPU 即可，无需 GPU）。输入标准蛋白结构
（protein_structure@1）与配体 SDF（ligand_structure@1，可多分子批量），输出
逐配体亲和力表（molecule_table@1）、最佳对接构象（ligand_structure@1）和运行报告。

镜像由 ``deploy/model-images/k8s/vina/Dockerfile`` 构建；PDBQT 制备用 Meeko，
盒心取配体三维质心，盒尺寸默认 22 Å。

Downgrade 只删本迁移创建的 vina 工具，不动其它行。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "20261031_12"
down_revision = "20261031_11"
branch_labels = None
depends_on = None

REGISTRY = "10.202.2.228:30500"
TIMEOUT_SEC = 1800
SLUG = "autodock-vina-docking"


def _has_tables(bind) -> bool:
    names = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions", "users"}.issubset(names)


def _resolve_owner_id(bind) -> str | None:
    row = bind.execute(
        sa.text("SELECT id FROM users WHERE role = 'admin' ORDER BY created_at ASC LIMIT 1")
    ).first()
    if row:
        return str(row[0])
    row = bind.execute(sa.text("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")).first()
    return str(row[0]) if row else None


def _model() -> dict:
    image_digest = "sha256:0788db8da9d7b84423cebe5986fceb898b89a0b58b97bd5c10386abfd6c0e50b"
    image = f"{REGISTRY}/aidd/compute-vina@{image_digest}"
    parameters_schema = {
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
    inputs = [
        {
            "name": "protein_pdb",
            "title": "蛋白结构",
            "type": "protein_structure@1",
            "required": True,
            "role_preferences": ["prepared_pdb", "structure_file"],
        },
        {
            "name": "ligand_sdf",
            "title": "配体结构（SDF，可多分子批量）",
            "type": "ligand_structure@1",
            "required": True,
            "role_preferences": ["structure_file"],
        },
    ]
    outputs = [
        {"name": "docking_results", "type": "molecule_table@1", "cardinality": "one", "required": True},
        {"name": "docked_poses", "type": "ligand_structure@1", "cardinality": "one", "required": True},
        {"name": "report", "type": "run_report@1", "cardinality": "one", "required": False},
    ]
    manifest = {
        "api_version": "aidd.sciminer/tool-package",
        "kind": "ToolPackage",
        "metadata": {
            "slug": SLUG,
            "name": "AutoDock Vina 分子对接",
            "version": "1.0.0",
            "description": "AutoDock Vina 分子对接：蛋白结构 + 配体 SDF（可多分子批量），输出逐配体亲和力与最佳构象。",
        },
        "artifacts": {"inputs": inputs, "outputs": outputs},
        "parameters_schema": parameters_schema,
        "runtime": {
            "python": "3.10",
            "cuda": None,
            "executor_support": ["k8s_job"],
            "selection_policy": "CPU 计算，优先调度到具备充足 CPU 的 k8s 节点",
            "weights": {"manifest_uri": "", "manifest_sha256": "", "mounts": []},
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": image,
                    "image_digest": image_digest,
                    "includes": ["python", "vina", "meeko", "rdkit"],
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
                "name": "cpu",
                "accelerator": "cpu",
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
        "gpu_required": False,
        "gpu_memory_required_mb": 0,
        "cpu_limit": 4,
        "memory_limit": "8Gi",
        "parameters_schema": parameters_schema,
        "runtime": {},
    }
    return {
        "slug": SLUG,
        "name": "AutoDock Vina 分子对接",
        "description": "AutoDock Vina 分子对接：蛋白结构 + 配体 SDF（可多分子批量），输出逐配体亲和力与最佳构象。",
        "version": "1.0.0",
        "changelog": "AutoDock Vina 1.2.7 真实模型包（K8s CPU）",
        "config": config,
        "gpu_required": False,
        "gpu_memory_mb": 0,
    }


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
                "current_version_id = :version_id, gpu_required = false, gpu_memory_mb = 0, "
                "timeout_sec = :timeout_sec, updated_at = :now WHERE id = :tool_id"
            ),
            {
                "owner_id": owner_id,
                "name": model["name"],
                "description": model["description"],
                "version_id": version_id,
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
                "false, 0, :timeout_sec)"
            ),
            {
                "id": tool_id,
                "now": now,
                "owner_id": owner_id,
                "name": model["name"],
                "slug": slug,
                "description": model["description"],
                "version_id": version_id,
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
    _upsert(bind, _model(), owner_id, datetime.utcnow())


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    row = bind.execute(sa.text("SELECT id FROM tools WHERE slug = :slug"), {"slug": SLUG}).first()
    if not row:
        return
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
