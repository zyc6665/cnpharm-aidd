"""Legacy Tool Package semantic type migration tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tool_packages.legacy_migration import migrate_legacy_artifact_type  # noqa: E402
from app.tool_packages.schemas import ToolPackageV2Manifest  # noqa: E402
from app.tool_packages.validator import validate_tool_package  # noqa: E402


def test_legacy_migration_maps_protein_aliases_to_standard_ref() -> None:
    assert migrate_legacy_artifact_type("protein_pdb").standard_type == "protein_structure@1"
    assert migrate_legacy_artifact_type("protein_structure").standard_type == "protein_structure@1"


def test_legacy_migration_maps_pocket_aliases_to_standard_ref() -> None:
    assert migrate_legacy_artifact_type("pocket_pdb").standard_type == "binding_pocket@1"
    assert migrate_legacy_artifact_type("pocket_result").standard_type == "binding_pocket@1"


def test_legacy_migration_requires_explicit_choice_for_generated_ligand() -> None:
    result = migrate_legacy_artifact_type("generated_ligand")

    assert result.standard_type is None
    assert result.requires_choice is True
    assert "ligand_structure@1" in result.candidates
    assert "molecule_table@1" in result.candidates
    assert any("generated_ligand" in warning for warning in result.warnings)


def test_v2_validator_rejects_legacy_alias_even_when_migration_exists() -> None:
    manifest = ToolPackageV2Manifest.model_validate(
        {
            "api_version": "aidd.sciminer/tool-package.v2",
            "kind": "ToolPackage",
            "metadata": {
                "slug": "legacy-alias-tool",
                "name": "Legacy Alias Tool",
                "version": "1.0.0",
            },
            "artifacts": {
                "inputs": [{"name": "protein", "type": "protein_pdb"}],
                "outputs": [{"name": "pocket", "type": "pocket_result"}],
            },
            "variants": [
                {
                    "name": "cpu",
                    "accelerator": "cpu",
                    "executor_types": ["cli"],
                    "entrypoint": ["/app/run"],
                }
            ],
        }
    )

    result = validate_tool_package(manifest)

    assert result.is_valid is False
    assert any("protein_pdb" in error for error in result.errors)
    assert any("pocket_result" in error for error in result.errors)
