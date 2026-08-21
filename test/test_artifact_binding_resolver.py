"""Artifact binding resolver policy tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.artifact_binding_resolver import (  # noqa: E402
    resolve_artifact_binding_policy,
)


def test_raw_protein_that_requires_preparation_returns_preparation_decision() -> None:
    decision = resolve_artifact_binding_policy(
        input_slot={
            "name": "protein",
            "type": "protein_structure@1",
            "readiness_policy": "require_prepared",
        },
        artifact_type="protein_structure@1",
        available_roles={"structure_file"},
        metadata={"preparation_status": "raw"},
    )

    assert decision.status == "needs_preparation"
    assert decision.input_name == "protein"
    assert decision.standard_type == "protein_structure@1"
    assert decision.selected_role is None
    assert decision.suggested_tool_slug == "builtin-protein-preparation"


def test_prepared_protein_selects_prepared_pdb_for_prepared_policy() -> None:
    decision = resolve_artifact_binding_policy(
        input_slot={
            "name": "protein",
            "type": "protein_structure@1",
            "readiness_policy": "require_prepared",
        },
        artifact_type="protein_structure@1",
        available_roles={"structure_file", "prepared_pdb"},
        metadata={"preparation_status": "prepared"},
    )

    assert decision.status == "ready"
    assert decision.selected_role == "prepared_pdb"
    assert decision.suggested_tool_slug is None


def test_receptor_policy_selects_receptor_pdbqt() -> None:
    decision = resolve_artifact_binding_policy(
        input_slot={
            "name": "receptor",
            "type": "protein_structure@1",
            "readiness_policy": "require_receptor",
        },
        artifact_type="protein_structure@1",
        available_roles={"structure_file", "prepared_pdb", "receptor_pdbqt"},
        metadata={"preparation_status": "prepared"},
    )

    assert decision.status == "ready"
    assert decision.selected_role == "receptor_pdbqt"


def test_ligand_policy_prefers_3d_sdf() -> None:
    decision = resolve_artifact_binding_policy(
        input_slot={
            "name": "ligand",
            "type": "ligand_structure@1",
            "readiness_policy": "prefer_3d_ligand",
        },
        artifact_type="ligand_structure@1",
        available_roles={"structure_file", "structure_3d_sdf"},
        metadata={"structure_3d_source": "pubchem_3d"},
    )

    assert decision.status == "ready"
    assert decision.selected_role == "structure_3d_sdf"


def test_ligand_policy_converts_2d_only_ligand() -> None:
    decision = resolve_artifact_binding_policy(
        input_slot={
            "name": "ligand",
            "type": "ligand_structure@1",
            "readiness_policy": "prefer_3d_ligand",
        },
        artifact_type="ligand_structure@1",
        available_roles={"structure_2d_sdf"},
        metadata={"structure_3d_source": "2d_only"},
    )

    assert decision.status == "needs_conversion"
    assert decision.selected_role is None
    assert decision.suggested_tool_slug == "builtin-rdkit-conformer"


def test_type_mismatch_is_invalid() -> None:
    decision = resolve_artifact_binding_policy(
        input_slot={
            "name": "protein",
            "type": "protein_structure@1",
            "readiness_policy": "allow_raw",
        },
        artifact_type="ligand_structure@1",
        available_roles={"structure_file"},
        metadata={},
    )

    assert decision.status == "invalid"
    assert decision.selected_role is None
    assert decision.suggested_tool_slug is None
