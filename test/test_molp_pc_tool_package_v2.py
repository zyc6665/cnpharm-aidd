"""MolP-PC Tool Package v2 standard Artifact contract tests."""

from __future__ import annotations

import importlib.util
import json
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


PACKAGE_ROOT = PROJECT_ROOT / "example" / "MolP-PC" / "tool-package-v2"
REQUIRED_FILES = {
    "tool.yaml",
    "README.md",
    "AGENTS.md",
    "examples/input/molecules/smiles.csv",
    "examples/input/molecules/metadata.json",
    "examples/request.json",
    "examples/output/artifacts/properties/molp_pc_predictions.csv",
    "examples/output/artifacts/properties/metadata.json",
    "examples/output/reports/report.json",
    "runner/entrypoint.sh",
    "runner/platform_adapter.py",
    "schemas/parameters.schema.json",
    "schemas/result.v2.example.json",
    "tests/test_contract.py",
}


def _load_adapter():
    path = PACKAGE_ROOT / "runner" / "platform_adapter.py"
    spec = importlib.util.spec_from_file_location("molp_pc_platform_adapter", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_molp_pc_v2_package_contains_platformization_files():
    missing = sorted(path for path in REQUIRED_FILES if not (PACKAGE_ROOT / path).is_file())

    assert missing == []


def test_molp_pc_v2_manifest_uses_standard_molecule_table_contract():
    manifest = load_tool_package(PACKAGE_ROOT)
    result = validate_tool_package(manifest)

    assert isinstance(manifest, ToolPackageV2Manifest)
    assert result.is_valid is True, result.errors
    assert [(item.name, item.type) for item in manifest.artifacts.inputs] == [
        ("molecules", "molecule_table@1")
    ]
    assert [(item.name, item.type, item.cardinality) for item in manifest.artifacts.outputs] == [
        ("properties", "molecule_table@1", "one"),
        ("report", "run_report@1", "one"),
    ]
    assert "device" not in set(manifest.parameters_schema.get("required", []))
    for variant in manifest.variants:
        assert (PACKAGE_ROOT / variant.entrypoint[0]).is_file()


def test_molp_pc_v2_golden_result_validates_prediction_table_roles():
    parsed = parse_standard_result(
        result_path=PACKAGE_ROOT / "schemas" / "result.v2.example.json",
        output_dir=PACKAGE_ROOT / "examples" / "output",
        declared_outputs=[
            DeclaredArtifactOutput(name="properties", type="molecule_table@1"),
            DeclaredArtifactOutput(name="report", type="run_report@1", required=False),
        ],
    )

    properties = next(
        artifact for artifact in parsed.artifacts if artifact.output_name == "properties"
    )

    assert properties.type == "molecule_table@1"
    assert set(properties.files) == {"table_file", "metadata_json"}
    assert properties.metadata["molecule_id_field"] == "SMILES"
    assert properties.metadata["source_task_id"] == "example-task"


def test_molp_pc_adapter_wraps_legacy_prediction_csv_as_result_v2(tmp_path: Path):
    raw_dir = tmp_path / "legacy-output"
    output_dir = tmp_path / "output"
    raw_dir.mkdir()
    (raw_dir / "cb_data_result.csv").write_text("SMILES,F20\nCCO,0.9\n", encoding="utf-8")

    result = _load_adapter().adapt_legacy_outputs(
        request={
            "task": {
                "id": "task-001",
                "tool_slug": "molp-pc-property-prediction",
                "tool_version": "1.0.0",
            },
            "inputs": {
                "molecules": {
                    "artifact_version_id": "input-version",
                    "type": "molecule_table@1",
                    "files": {
                        "table_file": {
                            "path": "input/molecules/smiles.csv",
                            "sha256": "a" * 64,
                            "content_type": "text/csv",
                        }
                    },
                    "metadata": {"molecule_id_field": "SMILES"},
                }
            },
        },
        raw_output_dir=raw_dir,
        output_dir=output_dir,
    )

    assert result["result_version"] == "aidd.sciminer/result.v2"
    assert result["artifacts"]["properties"]["type"] == "molecule_table@1"
    assert set(result["artifacts"]["properties"]["files"]) == {"table_file", "metadata_json"}
    assert (output_dir / "artifacts/properties/molp_pc_predictions.csv").is_file()
    assert (output_dir / "artifacts/properties/metadata.json").is_file()
    assert result["artifacts"]["properties"]["metadata"]["molecule_id_field"] == "SMILES"


def test_molp_pc_v2_package_does_not_embed_deployment_secrets_or_host_paths():
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
