"""Normalize legacy tool semantic labels to platform standard Artifact refs."""

from __future__ import annotations

from app.artifact_standards.registry import is_standard_artifact_ref


LEGACY_SEMANTIC_TYPE_ALIASES: dict[str, str] = {
    "protein_pdb": "protein_structure@1",
    "protein_structure": "protein_structure@1",
    "pocket_pdb": "binding_pocket@1",
    "pocket_structure": "binding_pocket@1",
    "binding_pocket": "binding_pocket@1",
    "generated_ligand": "ligand_structure@1",
    "ligand_pdb": "ligand_structure@1",
    "ligand_structure": "ligand_structure@1",
    "docking_pose": "ligand_structure@1",
    "docking_pose_diffdock": "ligand_structure@1",
    "docking_pose_gnina": "ligand_structure@1",
    "docking_pose_smina": "ligand_structure@1",
    "optimized_lead": "ligand_structure@1",
    "smiles_csv": "molecule_table@1",
    "ranking_csv": "molecule_table@1",
    "database_query_result": "molecule_table@1",
    "docking_report": "run_report@1",
    "affinity_report": "run_report@1",
    "property_report": "run_report@1",
    "admet_report": "run_report@1",
    "toxicity_report": "run_report@1",
    "synthetic_accessibility": "run_report@1",
    "interaction_report": "run_report@1",
    "run_report": "run_report@1",
}


def normalize_platform_artifact_type(value: str) -> str:
    """Return the platform-facing standard Artifact ref for a type label."""
    if is_standard_artifact_ref(value):
        return value
    return LEGACY_SEMANTIC_TYPE_ALIASES.get(value, value)


def is_supported_platform_artifact_type(value: str) -> bool:
    """Check whether a type label resolves to a known platform standard Artifact."""
    return is_standard_artifact_ref(normalize_platform_artifact_type(value))
