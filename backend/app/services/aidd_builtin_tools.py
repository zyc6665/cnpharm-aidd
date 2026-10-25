"""Persisted platform tools backing supported AIDD built-in capabilities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.tools.capabilities import AIDD_TOOL_CAPABILITIES
from app.common.exceptions import ValidationException
from app.models.tools import Tool, ToolProviderType, ToolReviewStatus, ToolStatus, ToolVersion
from app.models.users import User


def _capability_config(tool_slug: str) -> dict:
    capability = AIDD_TOOL_CAPABILITIES.get(tool_slug)
    if not capability or not capability.virtual:
        raise ValidationException(f"不支持的 AIDD 内置工具: {tool_slug}")

    config = {
        "type": "builtin",
        "builtin_slug": tool_slug,
        "timeout_sec": 600,
        "agent_capability": {
            "enabled": True,
            "capability": capability.capability,
            "stage": capability.stage,
            "inputs": [
                {
                    "semantic_type": item.semantic_type,
                    "field": item.field,
                    "required": item.required,
                    "accepted_extensions": list(item.accepted_extensions),
                }
                for item in capability.inputs
            ],
            "outputs": [
                {
                    "semantic_type": item.semantic_type,
                    "source": item.source,
                    "path": item.path,
                    "required": item.required,
                    "match": (
                        {
                            "extension": item.match.extension,
                            "filename_contains_any": list(item.match.filename_contains_any),
                            "content_type": item.match.content_type,
                        }
                        if item.match
                        else None
                    ),
                }
                for item in capability.outputs
            ],
            "defaults": dict(capability.defaults),
        },
    }
    if tool_slug == "builtin-protein-preparation":
        config["input_schema"] = {
            "type": "object",
            "description": "使用 PDBFixer、OpenMM 和 Open Babel 的开源蛋白结构预处理流程。",
            "properties": {
                "ph": {"type": "number", "title": "Target pH", "minimum": 0, "maximum": 14, "default": 7.4},
                "fill_missing_side_chains": {"type": "boolean", "title": "Fill missing side chains", "default": True},
                "fill_missing_loops": {"type": "boolean", "title": "Fill missing loops", "default": True},
                "add_hydrogens": {"type": "boolean", "title": "Add hydrogens", "default": True},
                "optimize_hydrogen_bonding": {"type": "boolean", "title": "Optimize hydrogen bonding", "default": True},
                "remove_water": {"type": "boolean", "title": "Remove water", "default": True},
                "keep_metals": {"type": "boolean", "title": "Keep metal ions", "default": True},
                "keep_cofactors": {"type": "boolean", "title": "Keep cofactors", "default": True},
                "remove_non_target_ligands": {"type": "boolean", "title": "Remove non-target ligands", "default": True},
                "energy_minimization": {"type": "boolean", "title": "Energy minimization", "default": True},
            },
            "required": [],
        }
        config["artifacts"] = {
            "inputs": [
                {
                    "name": "protein",
                    "type": "protein_structure@1",
                    "required": True,
                    "role_preferences": ["structure_file", "raw_structure_file"],
                    "readiness_policy": "allow_raw",
                },
            ],
            "outputs": [
                {
                    "name": "prepared_protein",
                    "type": "protein_structure@1",
                    "required": True,
                    "provided_roles": ["prepared_pdb", "receptor_pdbqt", "preparation_report_json"],
                },
            ],
        }
    if tool_slug == "builtin-ligand-preparation":
        config["timeout_sec"] = 600
        config["resource_profile"] = {
            "tier": "medium",
            "cpu": 4,
            "memory_mb": 8192,
            "gpu": False,
        }
        config["input_schema"] = {
            "type": "object",
            "properties": {
                "smiles_column": {"type": "string", "title": "SMILES column", "default": "SMILES"},
                "name_column": {"type": "string", "title": "Name column", "default": "name"},
                "remove_explicit_hydrogens": {"type": "boolean", "title": "Remove explicit hydrogens", "default": True},
                "remove_disconnected_fragments": {"type": "boolean", "title": "Keep largest molecular fragment", "default": True},
                "normalize_structure": {"type": "boolean", "title": "Normalize structure", "default": True},
                "reionize": {"type": "boolean", "title": "Reionize", "default": True},
                "neutralize": {"type": "boolean", "title": "Neutralize", "default": True},
                "remove_pains": {"type": "boolean", "title": "Remove PAINS", "default": True},
                "remove_duplicates": {"type": "boolean", "title": "Remove duplicates", "default": True},
                "min_molecular_weight": {"type": "number", "title": "Minimum molecular weight", "minimum": 0},
                "max_molecular_weight": {"type": "number", "title": "Maximum molecular weight", "minimum": 0},
                "generate_3d": {"type": "boolean", "title": "Generate 3D conformers", "default": True},
                "drop_3d_failures": {"type": "boolean", "title": "Drop 3D generation failures", "default": True},
                "forcefield": {"type": "string", "title": "Force field", "enum": ["uff", "mmff"], "default": "uff"},
                "conformer_seed": {"type": "integer", "title": "Conformer random seed", "default": 20260930},
            },
            "required": [],
        }
        config["artifacts"] = {
            "inputs": [
                {
                    "name": "molecules",
                    "type": "molecule_table@1",
                    "required": True,
                    "role_preferences": ["table_file", "metadata_json"],
                    "readiness_policy": "allow_raw",
                },
            ],
            "outputs": [
                {"name": "molecules", "type": "molecule_table@1", "required": True},
                {"name": "ligands", "type": "ligand_structure@1", "required": True},
                {"name": "report", "type": "run_report@1", "required": True},
            ],
        }
    if tool_slug == "builtin-rdkit-conformer":
        config["timeout_sec"] = 600
        config["resource_profile"] = {
            "tier": "medium",
            "cpu": 4,
            "memory_mb": 8192,
            "gpu": False,
        }
        config["input_schema"] = {
            "type": "object",
            "properties": {
                "generate_3d": {"type": "boolean", "title": "Generate 3D conformers", "default": True},
                "drop_3d_failures": {"type": "boolean", "title": "Drop 3D generation failures", "default": True},
                "forcefield": {"type": "string", "title": "Force field", "enum": ["uff", "mmff"], "default": "mmff"},
                "conformer_seed": {"type": "integer", "title": "Conformer random seed", "default": 20260930},
            },
            "required": [],
        }
        config["artifacts"] = {
            "inputs": [
                {
                    "name": "ligand",
                    "type": "ligand_structure@1",
                    "required": True,
                    "role_preferences": ["structure_2d_sdf", "structure_file"],
                    "readiness_policy": "allow_raw",
                },
            ],
            "outputs": [
                {"name": "ligand", "type": "ligand_structure@1", "required": True},
                {"name": "report", "type": "run_report@1", "required": False},
            ],
        }
    if tool_slug in {"builtin-sdf-to-smiles-csv", "builtin-sdf-to-pdb"}:
        config["timeout_sec"] = 120
        config["resource_profile"] = {
            "tier": "light",
            "cpu": 1,
            "memory_mb": 512,
            "gpu": False,
        }
        config["artifacts"] = {
            "inputs": [
                {
                    "name": "ligand",
                    "type": "ligand_structure@1",
                    "required": True,
                    "role_preferences": ["structure_3d_sdf", "structure_file", "structure_2d_sdf"],
                    "readiness_policy": "prefer_3d_ligand",
                },
            ],
            "outputs": [
                (
                    {"name": "molecules", "type": "molecule_table@1", "required": True}
                    if tool_slug == "builtin-sdf-to-smiles-csv"
                    else {"name": "ligand", "type": "ligand_structure@1", "required": True}
                )
            ],
        }
    if tool_slug == "builtin-vina-docking":
        config["artifacts"] = {
            "inputs": [
                {
                    "name": "protein",
                    "type": "protein_structure@1",
                    "required": True,
                    "role_preferences": ["receptor_pdbqt", "prepared_pdb"],
                    "required_roles": ["receptor_pdbqt"],
                    "readiness_policy": "require_receptor",
                    "suggested_preparation_tool": "builtin-protein-preparation",
                },
                {
                    "name": "ligand",
                    "type": "ligand_structure@1",
                    "required": True,
                    "role_preferences": ["structure_3d_sdf", "structure_file"],
                    "readiness_policy": "prefer_3d_ligand",
                    "suggested_preparation_tool": "builtin-rdkit-conformer",
                },
            ],
            "outputs": [
                {"name": "report", "type": "run_report@1", "required": True},
                {"name": "ranking", "type": "molecule_table@1", "required": True},
            ],
        }
    if tool_slug == "builtin-rdkit-properties":
        config["timeout_sec"] = 120
        config["resource_profile"] = {
            "tier": "light",
            "cpu": 2,
            "memory_mb": 2048,
            "gpu": False,
        }
        config["artifacts"] = {
            "inputs": [
                {"name": "molecules", "type": "molecule_table@1", "required": True},
            ],
            "outputs": [
                {"name": "properties", "type": "molecule_table@1", "required": True},
                {"name": "report", "type": "run_report@1", "required": False},
            ],
        }
    return config


async def ensure_aidd_builtin_tool(
    db: AsyncSession,
    *,
    owner_id: str,
    tool_slug: str,
) -> Tool:
    """Return a published platform tool for a supported internal capability."""
    owner = await db.get(User, owner_id)
    if not owner:
        raise ValidationException("AIDD_SYSTEM_USER_ID 未指向有效用户")

    result = await db.execute(
        select(Tool)
        .options(selectinload(Tool.current_version))
        .where(Tool.slug == tool_slug)
    )
    existing = result.scalar_one_or_none()
    if existing:
        if not existing.current_version or existing.current_version.config.get("type") != "builtin":
            raise ValidationException(f"内置工具 slug 已被非内置工具占用: {tool_slug}")
        return existing

    tool = Tool(
        owner_id=owner_id,
        name=tool_slug.replace("builtin-", "AIDD ").replace("-", " ").title(),
        slug=tool_slug,
        description="AIDD 平台内置任务执行器",
        category="aidd",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        provider_type=ToolProviderType.PLATFORM.value,
        review_status=ToolReviewStatus.NOT_REQUIRED.value,
        timeout_sec=600,
    )
    db.add(tool)
    await db.flush()

    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        changelog="AIDD built-in task executor",
        config=_capability_config(tool_slug),
        is_active=True,
    )
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    await db.commit()

    result = await db.execute(
        select(Tool)
        .options(selectinload(Tool.current_version))
        .where(Tool.id == tool.id)
    )
    return result.scalar_one()
