"""LVpocket Tool Package v2 standard Artifact contract tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.execution.result_parser import parse_standard_result  # noqa: E402
from app.execution.standard_contracts import DeclaredArtifactOutput  # noqa: E402
from app.tool_packages.loader import load_tool_package  # noqa: E402
from app.tool_packages.schemas import ToolPackageV2Manifest  # noqa: E402
from app.tool_packages.validator import validate_tool_package  # noqa: E402


PACKAGE_ROOT = PROJECT_ROOT / "example" / "LVpocket" / "tool-package-v2"


def test_lvpocket_v2_manifest_declares_standard_binding_pocket_contract():
    manifest = load_tool_package(PACKAGE_ROOT)
    result = validate_tool_package(manifest)

    assert isinstance(manifest, ToolPackageV2Manifest)
    assert result.is_valid is True, result.errors
    assert manifest.artifacts.inputs[0].type == "protein_structure@1"
    assert manifest.artifacts.outputs[0].name == "pocket"
    assert manifest.artifacts.outputs[0].type == "binding_pocket@1"
    for variant in manifest.variants:
        entrypoint = PACKAGE_ROOT / variant.entrypoint[0]
        assert entrypoint.is_file()


def test_lvpocket_v2_golden_result_validates_required_binding_pocket_roles():
    parsed = parse_standard_result(
        result_path=PACKAGE_ROOT / "schemas" / "result.v2.example.json",
        output_dir=PACKAGE_ROOT / "examples" / "output",
        declared_outputs=[
            DeclaredArtifactOutput(name="pocket", type="binding_pocket@1"),
            DeclaredArtifactOutput(name="report", type="run_report@1", required=False),
        ],
    )

    pocket = next(artifact for artifact in parsed.artifacts if artifact.output_name == "pocket")

    assert pocket.type == "binding_pocket@1"
    assert set(pocket.files) == {
        "residue_pocket_pdb",
        "atom_pocket_pdb",
        "pocket_metadata_json",
    }
