"""GCDM Tool Package v2 standard Artifact contract tests."""

from __future__ import annotations

import re
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


PACKAGE_ROOT = PROJECT_ROOT / "example" / "GCDM" / "tool-package-v2"
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


def test_gcdm_v2_package_contains_platformization_files():
    missing = sorted(path for path in REQUIRED_FILES if not (PACKAGE_ROOT / path).is_file())

    assert missing == []


def test_gcdm_v2_manifest_consumes_binding_pocket_and_emits_ligands():
    manifest = load_tool_package(PACKAGE_ROOT)
    result = validate_tool_package(manifest)

    assert isinstance(manifest, ToolPackageV2Manifest)
    assert result.is_valid is True, result.errors
    assert manifest.metadata.slug == "gcdm-pocket-generation"
    assert [(item.name, item.type) for item in manifest.artifacts.inputs] == [
        ("pocket", "binding_pocket@1")
    ]
    assert [(item.name, item.type, item.cardinality) for item in manifest.artifacts.outputs] == [
        ("molecules", "molecule_table@1", "one"),
        ("ligands", "ligand_structure@1", "many"),
        ("report", "run_report@1", "one"),
    ]
    assert "device" not in set(manifest.parameters_schema.get("required", []))
    for variant in manifest.variants:
        assert variant.entrypoint == ["runner/platform_run_v2.sh"]
        assert (PACKAGE_ROOT / variant.entrypoint[0]).is_file()
    assert not (PACKAGE_ROOT / "runner" / "platform_adapter.py").exists()


def test_gcdm_v2_golden_result_links_molecule_table_to_ligands():
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
    assert artifacts_by_ref["report"].type == "run_report@1"
    assert {"from": "molecules", "to": "ligands[0]", "type": "contains"} in parsed.relations
    assert {"from": "report", "to": "molecules", "type": "describes"} in parsed.relations


def test_gcdm_v2_package_does_not_embed_deployment_secrets_or_host_paths():
    text_suffixes = {"", ".json", ".md", ".py", ".sh", ".yaml", ".yml"}
    content = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PACKAGE_ROOT.rglob("*")
        if path.is_file() and path.suffix in text_suffixes
    )

    secret_assignment = r"(?i)(password|secret|access[_-]?key)\s*[:=]\s*[^${<\s][^\s]*"
    assert not re.search(secret_assignment, content)
    assert not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", content)
    assert not re.search(r"(?m)(?:^|[\s:'\"])/(?:home|root|data|mnt|opt|srv)/", content)
