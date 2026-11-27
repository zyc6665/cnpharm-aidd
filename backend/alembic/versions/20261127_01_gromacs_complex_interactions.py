"""GROMACS 镜像 1.1.0：蛋白-小分子复合物 MD（GAFF2/acpype + 自备 ITP）与相互作用分析。

Revision ID: 20261127_01
Revises: 20261125_02
Create Date: 2026-11-27

升级 ``gromacs-md`` 镜像至 ``1.1.0``（``@sha256:00273d5ac2aa054971d8026ac5b83f166e75a318951b82e7672d57b5e405b70a``）：
- 镜像内置 Python 3.11 + AmberTools + acpype + RDKit + MDAnalysis + ProLIF + MDTraj + NetworkX；
- ``tool_package_manifest.artifacts.inputs`` 增加可选 ``ligand_sdf``（``ligand_structure@1``）；
- ``parameters_schema`` 补充 ``force_field`` / ``ligand_resname`` / ``charge_method`` / ``net_charge`` / ``analysis_stride``；
- 对外产出兼容旧版 ``md_trajectory@1``，并新增可选 ``contacts_csv`` 与 ``interactions_json``。

Downgrade 对称恢复 ``20261110_01`` 的 ``1.0.1`` digest、输入槽位、参数契约与 changelog。
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json

import sqlalchemy as sa
from alembic import op

revision = "20261127_01"
down_revision = "20261125_02"
branch_labels = None
depends_on = None

SLUG = "gromacs-md"
OLD_DIGEST = "sha256:cee36ec427a4665f2e9aecf0cd7cf96bc313968e0798fa1c0c9282aa28149855"
NEW_DIGEST = "sha256:24ebbfdd094a08f00f02bfca1147f3430ebf6e0a146b82e62b7943095794ae68"

OLD_VERSION = "1.0.1"
NEW_VERSION = "1.1.0"

OLD_CHANGELOG = (
    "镜像 1.0.1：gmx_MMPBSA 改为逐帧输出 7 列自由能（与前端契约一致）；"
    "GROMACS 补 gmx gyrate（Rg）与 gmx rmsf -res（逐残基 RMSF）"
)
NEW_CHANGELOG = (
    "镜像 1.1.0：内置 AmberTools/acpype 与 ProLIF/MDAnalysis/MDTraj，"
    "支持蛋白-小分子复合物 MD 与轨迹相互作用分析（contacts.csv / interactions.json）"
)

OLD_INPUTS = [
    {
        "name": "protein_pdb",
        "title": "蛋白/复合物结构（PDB）",
        "type": "protein_structure@1",
        "required": True,
        "role_preferences": ["prepared_pdb", "structure_file"],
    }
]

NEW_INPUTS = [
    *OLD_INPUTS,
    {
        "name": "ligand_sdf",
        "title": "小分子配体（SDF/MOL/MOL2/PDB，可选）",
        "type": "ligand_structure@1",
        "required": False,
        "role_preferences": ["structure_file"],
    },
]

OLD_SCHEMA = {
    "type": "object",
    "properties": {
        "nsteps": {
            "type": "integer",
            "minimum": 0,
            "maximum": 500000,
            "default": 2500,
            "title": "生产 MD 步数",
            "description": "2 fs/步；默认 2500 步 = 5 ps。",
        },
        "dt": {
            "type": "number",
            "minimum": 0.001,
            "maximum": 0.004,
            "default": 0.002,
            "title": "时间步长 (ps)",
        },
        "temperature": {
            "type": "number",
            "minimum": 250,
            "maximum": 400,
            "default": 300.0,
            "title": "温度 (K)",
        },
        "box_distance": {
            "type": "number",
            "minimum": 0.8,
            "maximum": 2.5,
            "default": 1.0,
            "title": "盒边距 (nm)",
        },
        "water_model": {
            "type": "string",
            "default": "tip3p",
            "title": "水模型",
        },
        "device": {
            "type": "string",
            "enum": ["auto", "cpu", "gpu"],
            "default": "auto",
        },
    },
    "additionalProperties": False,
}

NEW_SCHEMA = {
    "type": "object",
    "properties": {
        **OLD_SCHEMA["properties"],
        "force_field": {
            "type": "string",
            "enum": ["amber99sb-ildn", "charmm36"],
            "default": "amber99sb-ildn",
            "title": "蛋白力场",
        },
        "ligand_resname": {
            "type": "string",
            "default": "LIG",
            "minLength": 1,
            "maxLength": 3,
            "title": "配体残基名",
            "description": "1-3 位大写字母/数字（需避开标准氨基酸与水/离子保留名）。",
        },
        "charge_method": {
            "type": "string",
            "enum": ["bcc", "gas"],
            "default": "bcc",
            "title": "配体电荷方法",
            "description": "acpype/antechamber 电荷估算方式（AM1-BCC 或 Gasteiger）。",
        },
        "net_charge": {
            "type": "integer",
            "minimum": -10,
            "maximum": 10,
            "title": "配体净电荷（可选）",
            "description": "留空时由 RDKit 按形式电荷自动推断。",
        },
        "analysis_stride": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 1,
            "title": "相互作用分析步幅",
            "description": "每隔多少帧采样一次相互作用指纹。",
        },
    },
    "additionalProperties": False,
}


def _has_tables(bind) -> bool:
    names = set(sa.inspect(bind).get_table_names())
    return {"tools", "tool_versions"}.issubset(names)


def _load_config(raw) -> dict | None:
    if isinstance(raw, dict):
        return copy.deepcopy(raw)
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _replace_digest(config_text: str, old_digest: str, new_digest: str) -> dict:
    return json.loads(config_text.replace(old_digest, new_digest))


def _rewrite(bind, *, forward: bool) -> None:
    row = bind.execute(
        sa.text(
            "SELECT v.id, v.config FROM tools t "
            "JOIN tool_versions v ON v.id = t.current_version_id "
            "WHERE t.slug = :slug"
        ),
        {"slug": SLUG},
    ).first()
    if not row:
        return

    version_id = str(row[0])
    parsed = _load_config(row[1])
    if parsed is None:
        return

    src_digest, dst_digest = (OLD_DIGEST, NEW_DIGEST) if forward else (NEW_DIGEST, OLD_DIGEST)
    config_text = json.dumps(parsed, ensure_ascii=False)
    if src_digest not in config_text:
        return
    updated = _replace_digest(config_text, src_digest, dst_digest)

    schema = copy.deepcopy(NEW_SCHEMA if forward else OLD_SCHEMA)
    inputs = copy.deepcopy(NEW_INPUTS if forward else OLD_INPUTS)
    updated["parameters_schema"] = schema
    manifest = updated.get("tool_package_manifest")
    if isinstance(manifest, dict):
        manifest.setdefault("artifacts", {})["inputs"] = inputs
        manifest["parameters_schema"] = copy.deepcopy(schema)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    config_expr = "CAST(:config AS json)" if bind.dialect.name == "postgresql" else ":config"
    bind.execute(
        sa.text(
            f"UPDATE tool_versions SET config = {config_expr}, version = :version, "
            "changelog = :changelog, updated_at = :now WHERE id = :id"
        ),
        {
            "id": version_id,
            "config": json.dumps(updated, ensure_ascii=False),
            "version": NEW_VERSION if forward else OLD_VERSION,
            "changelog": NEW_CHANGELOG if forward else OLD_CHANGELOG,
            "now": now,
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    _rewrite(bind, forward=True)


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_tables(bind):
        return
    _rewrite(bind, forward=False)
