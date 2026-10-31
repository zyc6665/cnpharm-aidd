"""Register TheraPainter peptide activity/toxicity prediction tool package.

Revision ID: 20261031_15
Revises: 20261031_14

TheraPainter（DualPep 预测头）对多肽序列做活性/毒性联合预测（CPU 可跑，GPU 更快）。
输入为多肽序列文本（``parameters.sequence``，每行一条，也接受 FASTA 文本），
输出逐序列指标表（``molecule_table@1``，molecule_id_field=seq）与运行报告。

模型代码与权重不烘进镜像：平台把节点目录 ``/data/zhouyc/kaiwu/TheraPainter``
以只读 hostPath 挂到容器 ``/opt/TheraPainter``；镜像
``deploy/model-images/k8s/therapainter/Dockerfile`` 只提供 Python/依赖与适配层。

Downgrade 只删本迁移创建的 therapainter 工具，不动其它行。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "20261031_15"
down_revision = "20261031_14"
branch_labels = None
depends_on = None

REGISTRY = "10.202.2.228:30500"
TIMEOUT_SEC = 1800
SLUG = "therapainter-peptide-prediction"
MODEL_HOST_PATH = "/data/zhouyc/kaiwu/TheraPainter"
IMAGE_DIGEST = "sha256:61d2d40853cc9153c73bbf42d4a16b76fd9966dd38f3b4194f0db7c7cd7f8a2c"


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
    image = f"{REGISTRY}/aidd/compute-therapainter@{IMAGE_DIGEST}"
    parameters_schema = {
        "type": "object",
        "properties": {
            "sequence": {
                "type": "string",
                "title": "多肽序列",
                "description": "单字母氨基酸序列，每行一条，也接受 FASTA 文本；单条长度 4-200。",
                "minLength": 4,
                "maxLength": 20000,
            },
            "prediction_mode": {
                "type": "string",
                "enum": ["joint", "activity", "toxicity"],
                "default": "joint",
                "title": "预测模式",
                "description": "joint=活性+毒性联合，activity=仅活性，toxicity=仅毒性。",
            },
            "deduplicate": {
                "type": "boolean",
                "default": True,
                "title": "去重",
                "description": "对输入序列去重后再预测。",
            },
            "batch_size": {
                "type": "integer",
                "minimum": 1,
                "maximum": 256,
                "default": 16,
                "title": "批大小",
                "description": "DualPep 推理批大小；显存不足时调小。",
            },
        },
        "required": ["sequence"],
        "additionalProperties": False,
    }
    inputs = []
    outputs = [
        {
            "name": "peptides",
            "type": "molecule_table@1",
            "cardinality": "one",
            "required": True,
        },
        {"name": "report", "type": "run_report@1", "cardinality": "one", "required": False},
    ]
    weights = {
        "manifest_uri": "",
        "manifest_sha256": "",
        "mounts": [
            {
                "name": "therapainter-model",
                "host_path": MODEL_HOST_PATH,
                "mount_path": "/opt/TheraPainter",
                "read_only": True,
            }
        ],
    }
    manifest = {
        "api_version": "aidd.sciminer/tool-package",
        "kind": "ToolPackage",
        "metadata": {
            "slug": SLUG,
            "name": "TheraPainter 多肽活性与毒性预测",
            "version": "1.0.0",
            "description": "TheraPainter（DualPep）预测多肽的活性、MIC 与毒性概率。",
        },
        "artifacts": {"inputs": inputs, "outputs": outputs},
        "parameters_schema": parameters_schema,
        "runtime": {
            "python": "3.11",
            "cuda": "12.4",
            "executor_support": ["k8s_job"],
            "selection_policy": "GPU 节点优先，CPU 可降级",
            "weights": weights,
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": image,
                    "image_digest": IMAGE_DIGEST,
                    "includes": ["python", "torch", "cuda", "therapainter"],
                },
                "fallback": {
                    "kind": "container",
                    "image": image,
                    "image_digest": IMAGE_DIGEST,
                    "includes": ["python", "therapainter"],
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
        "gpu_memory_required_mb": 8192,
        "cpu_limit": 4,
        "memory_limit": "16Gi",
        "parameters_schema": parameters_schema,
        "runtime": {"weights": weights},
    }
    return {
        "slug": SLUG,
        "name": "TheraPainter 多肽活性与毒性预测",
        "description": "TheraPainter（DualPep）预测多肽的活性、MIC 与毒性概率。",
        "version": "1.0.0",
        "changelog": "TheraPainter 真实模型包（K8s GPU，代码与权重 hostPath 挂载）",
        "config": config,
        "gpu_required": True,
        "gpu_memory_mb": 8192,
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
