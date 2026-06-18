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
    )
)

SEMANTIC_TYPE_ALIASES: dict[str, CanonicalSemanticType] = {
    "protein_structure": "protein_pdb",
    "pocket_structure": "pocket_pdb",
}

CANONICAL_AGENT_INPUT_TYPES: frozenset[str] = frozenset(
    (
        "protein_pdb",
        "pocket_pdb",
        "ligand_pdb",
        "smiles_csv",
        "generated_ligand",
    )
)


def normalize_semantic_type(value: str) -> str:
    """Return the canonical semantic type for a value or known legacy alias."""
    return SEMANTIC_TYPE_ALIASES.get(value, value)


def is_supported_semantic_type(value: str) -> bool:
    """Check whether a semantic type is canonical or a supported legacy alias."""
    return normalize_semantic_type(value) in CANONICAL_SEMANTIC_TYPES
