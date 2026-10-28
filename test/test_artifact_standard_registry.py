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
    list_standard_artifact_roles,
    load_relation_specs,
    load_standard_artifact_specs,
    parse_standard_ref,
    validate_standard_artifact_roles,
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
        "md_trajectory@1",
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


def test_protein_structure_metadata_schema_declares_external_database_fields():
    spec = get_standard_artifact_spec("protein_structure@1")
    properties = spec.metadata_schema["properties"]

    assert "chain_ids" in spec.metadata_schema["required"]
    assert properties["source_database"]["enum"] == ["rcsb", "manual", "tool_output"]
    assert properties["source_id"]["type"] == "string"
    assert properties["fetched_at"]["format"] == "date-time"


def test_protein_structure_declares_preparation_file_roles():
    spec = get_standard_artifact_spec("protein_structure@1")
    roles = {role.role: role for role in spec.file_roles}

    assert roles["structure_file"].primary is True
    assert roles["prepared_pdb"].required is False
    assert "pdb" in roles["prepared_pdb"].allowed_formats
    assert roles["receptor_pdbqt"].required is False
    assert "pdbqt" in roles["receptor_pdbqt"].allowed_formats
    assert roles["preparation_report_json"].required is False


def test_protein_structure_metadata_schema_declares_preparation_fields():
    spec = get_standard_artifact_spec("protein_structure@1")
    properties = spec.metadata_schema["properties"]

    assert properties["preparation_status"]["enum"] == ["raw", "prepared", "degraded", "failed"]
    assert properties["preparation_profile"]["type"] == "string"
    assert properties["ph"]["type"] == "number"
    assert properties["remove_water"]["type"] == "boolean"
    assert properties["keep_metals"]["type"] == "boolean"
    assert properties["keep_cofactors"]["type"] == "boolean"
    assert properties["remove_non_target_ligands"]["type"] == "boolean"
    assert properties["preparation_engine"]["type"] == "string"
    assert properties["source_artifact_version_id"]["type"] == "string"


def test_ligand_structure_keeps_primary_file_and_adds_optional_2d_3d_roles():
    spec = get_standard_artifact_spec("ligand_structure@1")

    roles = {role.role: role for role in spec.file_roles}
    required_roles = {role.role for role in spec.file_roles if role.required}
    primary_roles = {role.role for role in spec.file_roles if role.primary}

    assert required_roles == {"structure_file"}
    assert primary_roles == {"structure_file"}
    assert roles["structure_2d_sdf"].required is False
    assert roles["structure_3d_sdf"].required is False
    assert roles["structure_2d_sdf"].recommended_name == "ligand.2d.sdf"
    assert roles["structure_3d_sdf"].recommended_name == "ligand.3d.sdf"


def test_ligand_structure_metadata_schema_declares_external_database_fields():
    spec = get_standard_artifact_spec("ligand_structure@1")
    properties = spec.metadata_schema["properties"]

    assert spec.metadata_schema["required"] == ["ligand_id"]
    assert properties["source_database"]["enum"] == ["pubchem", "manual", "tool_output"]
    assert properties["structure_3d_source"]["enum"] == [
        "pubchem_3d",
        "rdkit_generated_3d",
        "2d_only",
    ]
    assert properties["canonical_smiles"]["type"] == "string"
    assert properties["hydrogens_added"]["type"] == "boolean"


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


def test_standard_role_registry_validates_roles_per_artifact_type():
    assert list_standard_artifact_roles("protein_structure@1") >= {
        "structure_file",
        "prepared_pdb",
        "receptor_pdbqt",
    }
    assert validate_standard_artifact_roles(
        "protein_structure@1",
        ["prepared_pdb", "receptor_pdbqt", "prepared_pdb"],
    ) == ["prepared_pdb", "receptor_pdbqt"]

    with pytest.raises(StandardArtifactRegistryError, match="Unknown file role"):
        validate_standard_artifact_roles("binding_pocket@1", ["receptor_pdbqt"])
