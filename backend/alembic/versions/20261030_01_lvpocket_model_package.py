"""Register the first real model package: LVpocket-2 pocket prediction.

Revision ID: 20261030_01
Revises: 20261029_01

与前一条 mock 包迁移的区别：这一条注册的是**真实模型**——镜像
``compute-lvpocket:2.0.0-cu122`` 在 4090 上以 ``device=2`` 真跑通过
（success / device gpu / 1 个口袋 / 17.35 s / 10 个产物）。

两个刻意选择：

1. **不带 ``tool_package_manifest``**。v2 包清单的完整契约（参数 schema、
   产物 adapter 方法）需要逐个模型校准，这一步先把「能提交、能起 Pod、
   能挂权重、能回传产物」打通；清单随后补。
2. **权重走 ``runtime.weights.mounts``（hostPath 直挂）**。权重 19 GB 不在镜像里
   （镜像 6.31 GB），由节点本地缓存提供。这是 ``docs/19`` §3 描述的开发期形态；
   对象存储拉取（initContainer）是后续步骤。

Downgrade 只删本迁移创建的行使，不动其它工具。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "20261030_01"
down_revision = "20261029_01"
branch_labels = None
depends_on = None


SLUG = "lvpocket-pocket-prediction"
TOOL_NAME = "LVpocket 口袋预测"
DESCRIPTION = (
    "基于 LVpocket-2（TensorFlow 2.15 + CUDA 12.2）的蛋白质口袋预测，"
    "输出按评分降序的口袋与口袋残基。权重外置在节点本地目录。"
)
CATEGORY = "model"
PROVIDER = "platform"
VERSION = "2.0.0"
TIMEOUT_SEC = 3600

IMAGE = (
    "10.202.2.228:30500/aidd/compute-lvpocket"
    "@sha256:d66e317d61f9f03580e613bd4ac689c4ebf37d64d42ab372cfea4d2eeaeb076a"
)
WEIGHT_HOST_PATH = "/data/zhouyc/model-cache/lvpocket/v2/new_best"
WEIGHT_MOUNT_PATH = "/opt/sciminer/model/new_best"

OPENBABEL_ROOT = "/usr/local/lib/python3.11/site-packages/openbabel"

PARAMETERS_SCHEMA = {
    "type": "object",
    "properties": {
        "model_choice": {
            "type": "string",
            "enum": ["auto", "all_scpdb", "alpha", "beta", "alpha_beta", "alpha_and_beta"],
            "default": "auto",
        },
        "device": {"type": "string", "enum": ["auto", "gpu", "cpu"], "default": "auto"},
    },
    "additionalProperties": False,
}


def _tool_package_manifest() -> dict:
    """Tool Package v2 清单。

    必须带 ``tool_package_manifest``：``backend/app/services/standard_input_slots.py``
    的 ``tool_accepts_materialized_standard_uploads()`` 只认 v2 清单，没有它
    ``standard_input_uploads`` 会被静默忽略，输入项拿不到 role/artifact_type，
    ``backend/app/tasks/executors/kubernetes_job.py`` 就会抛
    「Kubernetes inputs require a materialized standard ArtifactVersion」。
    即：光有扁平 type/image/runtime 能起 Pod，但走不通平台的标准输入物化。
    """
    return {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": SLUG,
            "name": TOOL_NAME,
            "version": VERSION,
            "description": "LVpocket-2 口袋预测（TensorFlow 2.15 + OpenBabel 3.1，GPU 推理）",
        },
        "artifacts": {
            "inputs": [
                {
                    "name": "protein",
                    "title": "蛋白结构",
                    "type": "protein_structure@1",
                    "required": True,
                    "role_preferences": ["prepared_pdb", "structure_file"],
                }
            ],
            "outputs": [
                {
                    "name": "pocket",
                    "type": "binding_pocket@1",
                    "cardinality": "one",
                    "required": True,
                },
                {
                    "name": "report",
                    "type": "run_report@1",
                    "cardinality": "one",
                    "required": False,
                },
            ],
        },
        "parameters_schema": PARAMETERS_SCHEMA,
        "runtime": {
            "python": "3.11",
            "cuda": "12.2",
            "executor_support": ["k8s_job"],
            "selection_policy": (
                "prefer container image by immutable digest; weights are mounted "
                "from the node-local cache"
            ),
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": IMAGE,
                    "image_digest": IMAGE.split("@", 1)[1],
                    "includes": ["python", "tensorflow", "openbabel", "ncbi-blast+"],
                },
                "fallback": {
                    "kind": "container",
                    "image": IMAGE,
                    "image_digest": IMAGE.split("@", 1)[1],
                    "includes": ["python"],
                },
            },
            "weights": {
                "mounts": [
                    {
                        "name": "lvpocket-weights",
                        "host_path": WEIGHT_HOST_PATH,
                        "mount_path": WEIGHT_MOUNT_PATH,
                        "read_only": True,
                    }
                ]
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
                "image": IMAGE,
                "entrypoint": [
                    "/usr/bin/tini",
                    "--",
                    "/opt/sciminer/platform_adaptor/entrypoint.sh",
                ],
                "validation_status": "validated",
                "hardware_validated": True,
            }
        ],
    }


def _tool_config() -> dict:
    """ToolVersion.config —— 任务执行器直接读这里的 type / image / runtime。"""
    return {
        "type": "k8s_job",
        "tool_package_manifest": _tool_package_manifest(),
        "image": IMAGE,
        "timeout_sec": TIMEOUT_SEC,
        "gpu_required": True,
        "gpu_memory_required_mb": 8192,
        "parameters_schema": PARAMETERS_SCHEMA,
        "runtime": {
            "weights": {
                "mounts": [
                    {
                        "name": "lvpocket-weights",
                        "host_path": WEIGHT_HOST_PATH,
                        "mount_path": WEIGHT_MOUNT_PATH,
                        "read_only": True,
                    }
                ]
            },
            "env": {
                "TF_CPP_MIN_LOG_LEVEL": "2",
                "BABEL_LIBDIR": f"{OPENBABEL_ROOT}/lib",
                "BABEL_DATADIR": f"{OPENBABEL_ROOT}/share/openbabel/3.1.0",
            },
        },
    }


def _resolve_owner_id(bind) -> str | None:
    row = bind.execute(
        sa.text(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at ASC LIMIT 1"
        )
    ).first()
    if row:
        return str(row[0])
    row = bind.execute(
        sa.text("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")
    ).first()
    return str(row[0]) if row else None


def _has_tables(bind) -> bool:
    names = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions", "users"}.issubset(names)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    owner_id = _resolve_owner_id(bind)
    if owner_id is None:
        # 还没有用户，工具无从挂载；等库里有人再跑一次迁移即可。
        return

    now = datetime.utcnow()
    config = json.dumps(_tool_config())

    row = bind.execute(
        sa.text("SELECT id, current_version_id FROM tools WHERE slug = :slug"),
        {"slug": SLUG},
    ).first()
    version_id = str(row[1]) if row and row[1] else str(uuid.uuid4())

    if row:
        tool_id = str(row[0])
        bind.execute(
            sa.text(
                "UPDATE tools SET owner_id = :owner_id, name = :name, description = :description, "
                "category = :category, status = 'published', is_public = true, "
                "provider_type = :provider, review_status = 'not_required', "
                "current_version_id = :version_id, gpu_required = true, "
                "gpu_memory_mb = :gpu_memory_mb, timeout_sec = :timeout_sec, updated_at = :now "
                "WHERE id = :tool_id"
            ),
            {
                "owner_id": owner_id,
                "name": TOOL_NAME,
                "description": DESCRIPTION,
                "category": CATEGORY,
                "provider": PROVIDER,
                "version_id": version_id,
                "gpu_memory_mb": 8192,
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
                ":category, 'published', true, :provider, 'not_required', :version_id, "
                "true, :gpu_memory_mb, :timeout_sec)"
            ),
            {
                "id": tool_id,
                "now": now,
                "owner_id": owner_id,
                "name": TOOL_NAME,
                "slug": SLUG,
                "description": DESCRIPTION,
                "category": CATEGORY,
                "provider": PROVIDER,
                "version_id": version_id,
                "gpu_memory_mb": 8192,
                "timeout_sec": TIMEOUT_SEC,
            },
        )

    exists = bind.execute(
        sa.text("SELECT 1 FROM tool_versions WHERE id = :id"), {"id": version_id}
    ).first()
    if exists:
        bind.execute(
            sa.text(
                "UPDATE tool_versions SET version = :version, changelog = :changelog, "
                "config = :config, is_active = true, deprecated = false, updated_at = :now "
                "WHERE id = :id"
            ),
            {
                "id": version_id,
                "version": VERSION,
                "changelog": "LVpocket-2 真实模型包（GPU，权重外置）",
                "config": config,
                "now": now,
            },
        )
    else:
        bind.execute(
            sa.text(
                "INSERT INTO tool_versions (id, created_at, updated_at, tool_id, version, "
                "changelog, config, is_active, deprecated) VALUES (:id, :now, :now, :tool_id, "
                ":version, :changelog, :config, true, false)"
            ),
            {
                "id": version_id,
                "now": now,
                "tool_id": tool_id,
                "version": VERSION,
                "changelog": "LVpocket-2 真实模型包（GPU，权重外置）",
                "config": config,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    row = bind.execute(
        sa.text("SELECT id FROM tools WHERE slug = :slug"), {"slug": SLUG}
    ).first()
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
