"""Pocket2Mol Tool Package v2 standard Artifact contract tests."""

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
from app.tool_packages.schemas import ToolPackageManifest  # noqa: E402
from app.tool_packages.validator import validate_tool_package  # noqa: E402


PACKAGE_ROOT = PROJECT_ROOT / "example" / "pocket2mol" / "tool-package"
REQUIRED_FILES = {
    "tool.yaml",
    "README.md",
    "AGENTS.md",
    "examples/request.json",
    "examples/output/result.json",
    "examples/output/artifacts/molecules/molecules.csv",
    "examples/output/artifacts/molecules/metadata.json",
    "examples/output/artifacts/ligands/ligand_001.sdf",
    "examples/output/reports/report.json",
    "runner/entrypoint.sh",
    "runner/platform_run_v2.sh",
    "schemas/parameters.schema.json",
    "schemas/result.v2.example.json",
}


def test_pocket2mol_v2_package_contains_platformization_files():
    missing = sorted(path for path in REQUIRED_FILES if not (PACKAGE_ROOT / path).is_file())

    assert missing == []


def test_pocket2mol_v2_manifest_consumes_standard_binding_pocket():
    manifest = load_tool_package(PACKAGE_ROOT)
    result = validate_tool_package(manifest)

    assert isinstance(manifest, ToolPackageManifest)
    assert result.is_valid is True, result.errors
    assert manifest.metadata.slug == "pocket2mol-pocket-ligand-generation"
    assert manifest.artifacts.inputs[0].name == "pocket"
    assert manifest.artifacts.inputs[0].type == "binding_pocket@1"
    assert [output.type for output in manifest.artifacts.outputs] == [
        "molecule_table@1",
        "ligand_structure@1",
        "run_report@1",
    ]
    assert manifest.artifacts.outputs[1].cardinality == "many"
    for variant in manifest.variants:
        assert variant.entrypoint == ["runner/platform_run_v2.sh"]
        entrypoint = PACKAGE_ROOT / variant.entrypoint[0]
        assert entrypoint.is_file()
    assert not (PACKAGE_ROOT / "runner" / "platform_adapter.py").exists()


def test_pocket2mol_v2_golden_result_links_table_to_ligands():
    parsed = parse_standard_result(
        result_path=PACKAGE_ROOT / "schemas" / "result.v2.example.json",
        output_dir=PACKAGE_ROOT / "examples" / "output",
        declared_outputs=[
            DeclaredArtifactOutput(name="molecules", type="molecule_table@1"),
            DeclaredArtifactOutput(
                name="ligands",
                type="ligand_structure@1",
                cardinality="many",
            ),
            DeclaredArtifactOutput(name="report", type="run_report@1", required=False),
        ],
    )

    artifacts_by_ref = {
        (
            artifact.output_name
            if artifact.index is None
            else f"{artifact.output_name}[{artifact.index}]"
        ): artifact
        for artifact in parsed.artifacts
    }

    assert artifacts_by_ref["molecules"].type == "molecule_table@1"
    assert artifacts_by_ref["ligands[0]"].type == "ligand_structure@1"
    assert artifacts_by_ref["ligands[1]"].type == "ligand_structure@1"
    assert artifacts_by_ref["report"].type == "run_report@1"
    assert {"from": "molecules", "to": "ligands[0]", "type": "contains"} in parsed.relations
    assert {"from": "molecules", "to": "ligands[1]", "type": "contains"} in parsed.relations
    assert {"from": "report", "to": "molecules", "type": "describes"} in parsed.relations
