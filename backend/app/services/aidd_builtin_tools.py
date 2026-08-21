"""Persisted platform tools backing supported AIDD built-in capabilities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.aidd.capabilities import AIDD_TOOL_CAPABILITIES
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
    if tool_slug == "builtin-fetch-pdb":
        config["timeout_sec"] = 120
        config["resource_profile"] = {
            "tier": "light",
            "cpu": 1,
            "memory_mb": 512,
            "gpu": False,
        }
        config["input_schema"] = {
            "type": "object",
            "properties": {
                "pdb_id": {
                    "type": "string",
                    "title": "PDB ID",
                    "description": "RCSB PDB entry ID, e.g. 1ABC",
                    "minLength": 4,
                    "maxLength": 12,
                }
            },
            "required": ["pdb_id"],
        }
        config["artifacts"] = {
            "inputs": [],
            "outputs": [
                {"name": "protein", "type": "protein_structure@1", "required": True},
                {"name": "report", "type": "run_report@1", "required": False},
            ],
        }
    if tool_slug == "builtin-fetch-ligand":
        config["timeout_sec"] = 120
        config["resource_profile"] = {
            "tier": "light",
            "cpu": 1,
            "memory_mb": 512,
            "gpu": False,
        }
        config["input_schema"] = {
            "type": "object",
            "properties": {
                "pubchem_cid": {
                    "type": "string",
                    "title": "PubChem CID",
                    "description": "PubChem compound CID, e.g. 2244",
                    "minLength": 1,
                    "maxLength": 32,
                }
            },
            "required": ["pubchem_cid"],
        }
        config["artifacts"] = {
            "inputs": [],
            "outputs": [
                {"name": "ligand", "type": "ligand_structure@1", "required": True},
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
        is_public=False,
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
