"""Register GROMACS molecular-dynamics and gmx_MMPBSA binding-free-energy tools.

Revision ID: 20261031_16
Revises: 20261031_15

GROMACS 2024.1（CUDA 版运行时裁剪进镜像）提供蛋白/复合物的短程分子动力学：
输入 ``protein_structure@1`` 的 PDB，输出 ``md_trajectory@1``（topology.pdb /
trajectory.dcd / analysis.csv / metadata.json）与运行报告。

gmx_MMPBSA（AmberTools 环境）对双链复合物做 MM/GBSA 结合自由能评估，内部先跑
短程 MD 生成轨迹，再调用 gmx_MMPBSA；输出 ``molecule_table@1``（binding_energy.csv）
与运行报告。AmberTools 环境通过只读 hostPath ``/data/gromacs`` 挂到 ``/opt/amber``。

Downgrade 只删除本迁移创建的两个工具，不动其它行。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "20261031_16"
down_revision = "20261031_15"
branch_labels = None
depends_on = None

REGISTRY = "10.202.2.228:30500"
IMAGE_DIGEST = "sha256:28f64b63cd573e41684d794aa6f34c615f16e9b340303e9c04eac5e6391cab95"
IMAGE = f"{REGISTRY}/aidd/compute-gromacs@{IMAGE_DIGEST}"
MMPBSA_IMAGE_DIGEST = "sha256:d61753513a21ae4909f44611f3f7cc568b1db589f9d8238107928532919e94fb"
MMPBSA_IMAGE = f"{REGISTRY}/aidd/compute-gmx-mmpbsa@{MMPBSA_IMAGE_DIGEST}"
AMBER_HOST_PATH = "/data/gromacs"


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


def _parameters_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "nsteps": {"type": "integer", "minimum": 0, "maximum": 500000, "default": 2500,
                       "title": "生产 MD 步数", "description": "2 fs/步；默认 2500 步 = 5 ps。"},
            "dt": {"type": "number", "minimum": 0.001, "maximum": 0.004, "default": 0.002,
                   "title": "时间步长 (ps)"},
            "temperature": {"type": "number", "minimum": 250, "maximum": 400, "default": 300.0,
                            "title": "温度 (K)"},
            "box_distance": {"type": "number", "minimum": 0.8, "maximum": 2.5, "default": 1.0,
                             "title": "盒边距 (nm)"},
            "water_model": {"type": "string", "default": "tip3p", "title": "水模型"},
            "device": {"type": "string", "enum": ["auto", "cpu", "gpu"], "default": "auto"},
        },
        "additionalProperties": False,
    }


def _inputs() -> list:
    return [{
        "name": "protein_pdb",
        "title": "蛋白/复合物结构（PDB）",
        "type": "protein_structure@1",
        "required": True,
        "role_preferences": ["prepared_pdb", "structure_file"],
    }]


def _manifest(slug: str, name: str, description: str, outputs: list, mount_amber: bool) -> dict:
    mounts = []
    if mount_amber:
        mounts.append({
            "name": "ambertools",
            "host_path": AMBER_HOST_PATH,
            "mount_path": "/opt/amber",
            "read_only": True,
        })
    weights = {"manifest_uri": "", "manifest_sha256": "", "mounts": mounts}
    image = MMPBSA_IMAGE if mount_amber else IMAGE
    image_digest = MMPBSA_IMAGE_DIGEST if mount_amber else IMAGE_DIGEST
    return {
        "api_version": "aidd.sciminer/tool-package",
        "kind": "ToolPackage",
        "metadata": {"slug": slug, "name": name, "version": "1.0.0", "description": description},
        "artifacts": {"inputs": _inputs(), "outputs": outputs},
        "parameters_schema": _parameters_schema(),
        "runtime": {
            "python": "3.11",
            "cuda": "12.1",
            "executor_support": ["k8s_job"],
            "selection_policy": "GROMACS 优先 GPU；gmx_MMPBSA 为 CPU 计算",
            "weights": weights,
            "artifacts": {
                "primary": {"kind": "container", "image": image, "image_digest": image_digest,
                            "includes": ["python", "gromacs", "cuda"]},
                "fallback": {"kind": "container", "image": image, "image_digest": image_digest,
                             "includes": ["python", "gromacs"]},
            },
            "cache_policy": {
                "key_fields": ["metadata.slug", "metadata.version",
                               "runtime.artifacts.primary.image_digest"],
                "mutable_host_paths_forbidden": True,
            },
        },
        "variants": [{
            "name": "nvidia-cuda",
            "accelerator": "nvidia_cuda",
            "executor_types": ["container"],
            "image": image,
            "entrypoint": ["/usr/bin/tini", "--", "/opt/sciminer/platform_adaptor/entrypoint.sh"],
            "validation_status": "validated",
            "hardware_validated": False,
        }],
    }


def _models() -> list:
    gromacs_outputs = [
        {"name": "trajectory", "type": "md_trajectory@1", "cardinality": "one", "required": True},
        {"name": "report", "type": "run_report@1", "cardinality": "one", "required": False},
    ]
    mmpbsa_outputs = [
        {"name": "binding_energy", "type": "molecule_table@1", "cardinality": "one", "required": True},
        {"name": "report", "type": "run_report@1", "cardinality": "one", "required": False},
    ]
    gromacs = {
        "slug": "gromacs-md",
        "name": "GROMACS 分子动力学模拟",
        "description": "GROMACS 2024.1 对蛋白/复合物做溶剂化、能量最小化、NVT/NPT 平衡与短程生产 MD。",
        "version": "1.0.0",
        "changelog": "GROMACS 2024.1 真实模型包（K8s GPU/CPU，镜像内含运行时）",
        "gpu_required": True,
        "gpu_memory_mb": 8192,
        "timeout_sec": 3600,
        "config": {
            "type": "k8s_job",
            "tool_package_manifest": _manifest(
                "gromacs-md", "GROMACS 分子动力学模拟",
                "GROMACS 2024.1 短程分子动力学模拟。", gromacs_outputs, False),
            "image": IMAGE,
            "timeout_sec": 3600,
            "gpu_required": True,
            "gpu_memory_required_mb": 8192,
            "cpu_limit": 4,
            "memory_limit": "16Gi",
            "parameters_schema": _parameters_schema(),
            "runtime": {"weights": {"manifest_uri": "", "manifest_sha256": "", "mounts": []}},
        },
    }
    mmpbsa = {
        "slug": "gmx-mmpbsa",
        "name": "gmx_MMPBSA 结合自由能评估",
        "description": "对双链蛋白/多肽复合物做短程 MD 后用 gmx_MMPBSA（MM/GBSA）评估结合自由能。",
        "version": "1.0.0",
        "changelog": "gmx_MMPBSA 1.6.3 真实模型包（AmberTools hostPath 挂载）",
        "gpu_required": False,
        "gpu_memory_mb": 0,
        "timeout_sec": 3600,
        "config": {
            "type": "k8s_job",
            "tool_package_manifest": _manifest(
                "gmx-mmpbsa", "gmx_MMPBSA 结合自由能评估",
                "gmx_MMPBSA（MM/GBSA）结合自由能评估。", mmpbsa_outputs, True),
            "image": MMPBSA_IMAGE,
            "timeout_sec": 3600,
            "gpu_required": False,
            "cpu_limit": 8,
            "memory_limit": "24Gi",
            "parameters_schema": _parameters_schema(),
            "runtime": {"weights": {"manifest_uri": "", "manifest_sha256": "",
                                    "mounts": [{"name": "ambertools", "host_path": AMBER_HOST_PATH,
                                                "mount_path": "/opt/amber", "read_only": True}]}},
        },
    }
    return [gromacs, mmpbsa]


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
                "current_version_id = :version_id, gpu_required = :gpu_required, gpu_memory_mb = :gpu_memory_mb, "
                "timeout_sec = :timeout_sec, updated_at = :now WHERE id = :tool_id"
            ),
            {
                "owner_id": owner_id,
                "name": model["name"],
                "description": model["description"],
                "version_id": version_id,
                "gpu_required": model["gpu_required"],
                "gpu_memory_mb": model["gpu_memory_mb"],
                "timeout_sec": model["timeout_sec"],
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
                ":gpu_required, :gpu_memory_mb, :timeout_sec)"
            ),
            {
                "id": tool_id,
                "now": now,
                "owner_id": owner_id,
                "name": model["name"],
                "slug": slug,
                "description": model["description"],
                "version_id": version_id,
                "gpu_required": model["gpu_required"],
                "gpu_memory_mb": model["gpu_memory_mb"],
                "timeout_sec": model["timeout_sec"],
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
    for model in _models():
        _upsert(bind, model, owner_id, now)


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    for model in _models():
        row = bind.execute(
            sa.text("SELECT id FROM tools WHERE slug = :slug"), {"slug": model["slug"]}
        ).first()
        if not row:
            continue
        tool_id = str(row[0])
        bind.execute(sa.text("DELETE FROM tool_capabilities WHERE tool_id = :tool_id"), {"tool_id": tool_id})
        bind.execute(sa.text("UPDATE tools SET current_version_id = NULL WHERE id = :tool_id"), {"tool_id": tool_id})
        bind.execute(sa.text("DELETE FROM tool_versions WHERE tool_id = :tool_id"), {"tool_id": tool_id})
        bind.execute(sa.text("DELETE FROM tools WHERE id = :tool_id"), {"tool_id": tool_id})
