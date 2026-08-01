"""Standard Artifact registry contract tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.artifact_standards.registry import (
    StandardArtifactRegistryError,
    get_standard_artifact_spec,
    is_standard_artifact_ref,
    load_relation_specs,
    load_standard_artifact_specs,
    parse_standard_ref,
    validate_relation_type,
)


def test_registry_loads_mvp_standard_artifact_types():
    specs = load_standard_artifact_specs()

    assert set(specs) == {
        "protein_structure@1",
        "binding_pocket@1",
        "molecule_table@1",
        "ligand_structure@1",
        "run_report@1",
    }


def test_binding_pocket_requires_standard_file_roles():
    spec = get_standard_artifact_spec("binding_pocket@1")

    required_roles = {role.role for role in spec.file_roles if role.required}
    primary_roles = {role.role for role in spec.file_roles if role.primary}

    assert required_roles == {
        "residue_pocket_pdb",
        "atom_pocket_pdb",
        "pocket_metadata_json",
    }
    assert primary_roles == {"residue_pocket_pdb"}


def test_relation_registry_allows_only_controlled_relation_types():
    relation_specs = load_relation_specs()

    assert set(relation_specs) == {
        "derived_from",
        "contains",
        "describes",
        "ranked_by",
        "validated_by",
        "visualized_by",
    }
    assert validate_relation_type("contains") == "contains"
    with pytest.raises(StandardArtifactRegistryError, match="Unknown relation type"):
        validate_relation_type("include")


def test_standard_ref_parser_rejects_unknowns_and_legacy_aliases():
    parsed = parse_standard_ref("protein_structure@1")

    assert parsed.type == "protein_structure"
    assert parsed.version == 1
    assert is_standard_artifact_ref("binding_pocket@1") is True
    assert is_standard_artifact_ref("pocket_pdb") is False

    with pytest.raises(StandardArtifactRegistryError, match="Unknown standard artifact type"):
        parse_standard_ref("pocket_pdb")
    with pytest.raises(StandardArtifactRegistryError, match="Unknown standard artifact type"):
        get_standard_artifact_spec("binding_pocket@2")
