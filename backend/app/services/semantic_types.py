"""Canonical semantic artifact types shared by Agent and workflow contracts."""

from __future__ import annotations

from typing import Literal


CanonicalSemanticType = Literal[
    "protein_pdb",
    "pocket_pdb",
    "generated_ligand",
    "ligand_pdb",
    "smiles_csv",
    "ranking_csv",
    "docking_pose",
    "docking_report",
    "affinity_report",
    "property_report",
    "optimized_lead",
    "admet_report",
    "toxicity_report",
    "synthetic_accessibility",
    "molecular_dynamics_trajectory",
    "interaction_report",
    "docking_pose_diffdock",
    "docking_pose_gnina",
    "docking_pose_smina",
    "database_query_result",
]

CANONICAL_SEMANTIC_TYPES: frozenset[str] = frozenset(
    (
        "protein_pdb",
        "pocket_pdb",
        "generated_ligand",
        "ligand_pdb",
        "smiles_csv",
        "ranking_csv",
        "docking_pose",
        "docking_report",
        "affinity_report",
        "property_report",
        "optimized_lead",
        "admet_report",
        "toxicity_report",
        "synthetic_accessibility",
        "molecular_dynamics_trajectory",
        "interaction_report",
        "docking_pose_diffdock",
        "docking_pose_gnina",
        "docking_pose_smina",
        "database_query_result",
    )
)

SEMANTIC_TYPE_ALIASES: dict[str, CanonicalSemanticType] = {
    "protein_structure": "protein_pdb",
    "pocket_structure": "pocket_pdb",
    "md_traj": "molecular_dynamics_trajectory",
    "trajectory": "molecular_dynamics_trajectory",
    "sa_score": "synthetic_accessibility",
    "synthetic_accessibility_score": "synthetic_accessibility",
    "interactions": "interaction_report",
    "interaction_fingerprint": "interaction_report",
    "chembl_result": "database_query_result",
    "pubchem_result": "database_query_result",
    "pdbbind_result": "database_query_result",
}

CANONICAL_AGENT_INPUT_TYPES: frozenset[str] = frozenset(
    (
        "protein_pdb",
        "pocket_pdb",
        "ligand_pdb",
        "smiles_csv",
        "generated_ligand",
        "database_query_result",
    )
)


def normalize_semantic_type(value: str) -> str:
    """Return the canonical semantic type for a value or known legacy alias."""
    return SEMANTIC_TYPE_ALIASES.get(value, value)


def is_supported_semantic_type(value: str) -> bool:
    """Check whether a semantic type is canonical or a supported legacy alias."""
    return normalize_semantic_type(value) in CANONICAL_SEMANTIC_TYPES
