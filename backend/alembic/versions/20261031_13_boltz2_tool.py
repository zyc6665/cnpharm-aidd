"""Register Boltz-2 protein structure prediction tool package.

Revision ID: 20261031_13
Revises: 20261031_12

Boltz-2 2.2.1 蛋白结构预测（GPU）。输入为单字母氨基酸序列（``parameters.sequence``），
输出标准蛋白结构（``protein_structure@1``）与运行报告（``run_report@1``）。

权重不烘进镜像：平台把节点上的 Boltz-2 缓存目录以只读 hostPath 挂到容器的
``/opt/boltz2_cache``（``boltz2_conf.ckpt`` / ``boltz2_aff.ckpt`` / ``mols/``）。
镜像由 ``deploy/model-images/k8s/boltz2/Dockerfile`` 构建。

Downgrade 只删本迁移创建的 boltz2 工具，不动其它行。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "20261031_13"
down_revision = "20261031_12"
branch_labels = None
depends_on = None

REGISTRY = "10.202.2.228:30500"
TIMEOUT_SEC = 3600
SLUG = "boltz2-structure-prediction"
WEIGHTS_HOST_PATH = "/data/zhouyc/k8s-model-build/boltz2_cache"


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


def _model(image_digest: str) -> dict:
    image = f"{REGISTRY}/aidd/compute-boltz2@{image_digest}"
    parameters_schema = {
        "type": "object",
        "properties": {
            "sequence": {
                "type": "string",
                "title": "蛋白序列",
                "description": "单字母氨基酸序列，可带 FASTA 头；长度 4-2000。",
                "minLength": 4,
                "maxLength": 2000,
            },
            "name": {
                "type": "string",
                "title": "任务名称",
                "default": "protein",
                "description": "用于输出文件命名的短名称。",
            },
            "sampling_steps": {
                "type": "integer",
                "minimum": 10,
                "maximum": 1000,
                "default": 200,
                "description": "扩散采样步数，越高越精细但越慢。",
            },
            "recycling_steps": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 3,
                "description": "结构回收（recycling）轮数。",
            },
            "diffusion_samples": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 1,
                "description": "扩散采样数；取第一个模型作为输出结构。",
            },
            "seed": {
                "type": "integer",
                "minimum": 0,
                "maximum": 2147483647,
                "default": 0,
                "description": "随机种子，便于复现。",
            },
        },
        "required": ["sequence"],
        "additionalProperties": False,
    }
    inputs: list[dict] = []
    outputs = [
        {
            "name": "predicted_structure",
            "type": "protein_structure@1",
            "cardinality": "one",
            "required": True,
        },
        {"name": "report", "type": "run_report@1", "cardinality": "one", "required": False},
    ]
    manifest = {
        "api_version": "aidd.sciminer/tool-package",
        "kind": "ToolPackage",
        "metadata": {
            "slug": SLUG,
            "name": "Boltz-2 蛋白结构预测",
            "version": "1.0.0",
            "description": "Boltz-2 从单字母序列预测蛋白三维结构，输出 PDB 与置信度报告。",
        },
        "artifacts": {"inputs": inputs, "outputs": outputs},
        "parameters_schema": parameters_schema,
        "runtime": {
            "python": "3.11",
            "cuda": "12.4",
            "executor_support": ["k8s_job"],
            "selection_policy": "按 GPU 显存选择具备 nvidia GPU 的 k8s 节点",
            "weights": {
                "manifest_uri": "",
                "manifest_sha256": "",
                "mounts": [
                    {
                        "name": "boltz2-cache",
                        "host_path": WEIGHTS_HOST_PATH,
                        "mount_path": "/opt/boltz2_cache",
                        "read_only": True,
                    }
                ],
            },
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": image,
                    "image_digest": image_digest,
                    "includes": ["python", "boltz", "torch", "cuda"],
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
        "gpu_memory_required_mb": 32768,
        "cpu_limit": 8,
        "memory_limit": "32Gi",
        "parameters_schema": parameters_schema,
        "runtime": {
            "weights": {
                "manifest_uri": "",
                "manifest_sha256": "",
                "mounts": [
                    {
                        "name": "boltz2-cache",
                        "host_path": WEIGHTS_HOST_PATH,
                        "mount_path": "/opt/boltz2_cache",
                        "read_only": True,
                    }
                ],
            }
        },
    }
    return {
        "slug": SLUG,
        "name": "Boltz-2 蛋白结构预测",
        "description": "Boltz-2 从单字母序列预测蛋白三维结构，输出 PDB 与置信度报告。",
        "version": "1.0.0",
        "changelog": "Boltz-2 2.2.1 真实模型包（K8s GPU，权重 hostPath 挂载）",
        "config": config,
        "gpu_required": True,
        "gpu_memory_mb": 32768,
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
    # 镜像摘要由构建脚本写入：构建后通过环境变量或替换此常量。
    image_digest = "sha256:83dc125a83120c746c95446cf3dd1c7cb2edafdf676953b7a14543235d7462eb"
    _upsert(bind, _model(image_digest), owner_id, datetime.utcnow())


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
