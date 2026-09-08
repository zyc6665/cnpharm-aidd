"""MolP-PC Tool Package v2 standard Artifact contract tests."""

from __future__ import annotations

import re
import sys
import json
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
    "docs/model-card.md",
    "docs/verification-record.md",
    "examples/input/molecules/smiles.csv",
    "examples/input/molecules/metadata.json",
    "examples/request.json",
    "examples/output/artifacts/properties/molp_pc_predictions.csv",
    "examples/output/artifacts/properties/metadata.json",
    "examples/output/reports/report.json",
    "runner/entrypoint.sh",
    "runner/platform_run_v2.sh",
    "schemas/parameters.schema.json",
    "schemas/result.v2.example.json",
}


def test_molp_pc_v2_package_contains_platformization_files():
    missing = sorted(path for path in REQUIRED_FILES if not (PACKAGE_ROOT / path).is_file())

    assert missing == []


def test_molp_pc_v2_manifest_uses_standard_molecule_table_contract():
    manifest = load_tool_package(PACKAGE_ROOT)
    result = validate_tool_package(manifest)

    assert isinstance(manifest, ToolPackageV2Manifest)
    assert result.is_valid is True, result.errors
    assert manifest.metadata.version == "0.1.1"
    assert "/0.1.1/" in manifest.runtime.artifacts.fallback.uri
    assert "/0.1.1/" in manifest.runtime.weights.manifest_uri
    assert [(item.name, item.type) for item in manifest.artifacts.inputs] == [
        ("molecules", "molecule_table@1")
    ]
    assert [(item.name, item.type, item.cardinality) for item in manifest.artifacts.outputs] == [
        ("properties", "molecule_table@1", "one"),
        ("report", "run_report@1", "one"),
    ]
    assert "device" not in set(manifest.parameters_schema.get("required", []))
    for variant in manifest.variants:
        assert variant.entrypoint == ["runner/platform_run_v2.sh"]
        assert (PACKAGE_ROOT / variant.entrypoint[0]).is_file()
    variants = {variant.name: variant for variant in manifest.variants}
    assert variants["cpu"].validation_status == "validated"
    assert variants["cpu"].hardware_validated is True
    assert variants["nvidia-cuda"].hardware_validated is False
    assert not (PACKAGE_ROOT / "runner" / "platform_adapter.py").exists()


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


def test_molp_pc_v2_scientific_metadata_declares_delivery_identity():
    metadata = json.loads(
        (PACKAGE_ROOT / "examples/output/artifacts/properties/metadata.json").read_text(
            encoding="utf-8"
        )
    )
    report = json.loads(
        (PACKAGE_ROOT / "examples/output/reports/report.json").read_text(encoding="utf-8")
    )

    assert metadata["model_name"] == "MolP-PC"
    assert metadata["model_version"] == "0.1.1"
    assert metadata["runtime_ref"] == "container:registry.example/sciminer/molp-pc-runtime@sha256:4444444444444444444444444444444444444444444444444444444444444444"
    assert metadata["weights_ref"] == "artifacts://model-weights/molp-pc-property-prediction/0.1.1/weights.json#sha256:6666666666666666666666666666666666666666666666666666666666666666"
    assert metadata["evidence_level"] == "engineering_smoke_only"
    assert metadata["applicability_domain_status"] == "unknown"
    assert metadata["unit_or_label_policy"] == "per_endpoint_definition_or_unknown"
    assert metadata["model_card_ref"] == "docs/model-card.md"
    assert metadata["verification_record_ref"] == "docs/verification-record.md"
    assert sorted(report["task_groups"]) == [
        "Absorption",
        "Distribution",
        "Ecotoxicity",
        "Excretion",
        "LD50",
        "Metabolism",
        "Tox21",
        "Toxicology",
    ]
    assert report["scientific_interpretation"]["prediction_kind"] == "basic_admet_prediction"
    assert report["scientific_interpretation"]["unit_or_label_policy"] == "per_endpoint_definition_or_unknown"
    assert "not scientific validation" in (PACKAGE_ROOT / "docs/verification-record.md").read_text(encoding="utf-8")


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
