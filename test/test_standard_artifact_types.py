"""Platform standard Artifact type normalization tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.artifact_standards.types import (  # noqa: E402
    normalize_platform_artifact_type,
    is_supported_platform_artifact_type,
)


@pytest.mark.parametrize(
    ("raw_type", "expected"),
    [
        ("protein_structure@1", "protein_structure@1"),
        ("binding_pocket@1", "binding_pocket@1"),
        ("protein_pdb", "protein_structure@1"),
        ("protein_structure", "protein_structure@1"),
        ("pocket_pdb", "binding_pocket@1"),
        ("pocket_structure", "binding_pocket@1"),
        ("generated_ligand", "ligand_structure@1"),
        ("ligand_pdb", "ligand_structure@1"),
        ("docking_pose", "ligand_structure@1"),
        ("smiles_csv", "molecule_table@1"),
        ("ranking_csv", "molecule_table@1"),
        ("property_report", "run_report@1"),
        ("admet_report", "run_report@1"),
        ("toxicity_report", "run_report@1"),
        ("run_report", "run_report@1"),
    ],
)
def test_platform_artifact_type_normalizes_legacy_semantic_aliases(
    raw_type: str,
    expected: str,
) -> None:
    assert normalize_platform_artifact_type(raw_type) == expected
    assert is_supported_platform_artifact_type(raw_type) is True


def test_unknown_platform_artifact_type_is_preserved_but_not_supported() -> None:
    assert normalize_platform_artifact_type("custom_vendor_blob") == "custom_vendor_blob"
    assert is_supported_platform_artifact_type("custom_vendor_blob") is False
