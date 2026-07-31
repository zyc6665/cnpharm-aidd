"""Contract tests for the production LVpocket reference Tool Package."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.tool_packages.loader import load_tool_package
from app.tool_packages.validator import validate_tool_package


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "example" / "LVpocket" / "tool-package"
LEGACY_INPUT = REPOSITORY_ROOT / "example" / "LVpocket" / "input" / "protein.pdb"


def _load_result_parser():
    parser_path = PACKAGE_ROOT / "runner" / "result_parser.py"
    spec = importlib.util.spec_from_file_location("lvpocket_result_parser", parser_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lvpocket_reference_package_is_valid_and_hardware_claims_are_truthful():
    package = load_tool_package(PACKAGE_ROOT)
    result = validate_tool_package(package)
    variants = {variant.accelerator.value: variant for variant in package.variants}

    assert result.is_valid is True, result.errors
    assert package.artifacts.inputs[0].semantic_type == "protein_structure"
    assert {item.artifact_type for item in package.artifacts.outputs} >= {
        "pocket_result",
        "run_report",
    }
    assert variants["cpu"].validation_status.value == "validated"
    assert variants["nvidia_cuda"].validation_status.value == "validated"
    assert variants["nvidia_cuda"].hardware_validated is True
    assert (
        variants["haiguang_dcu"].validation_status.value
        == "adapted_pending_hardware_validation"
    )
    assert variants["haiguang_dcu"].hardware_validated is False


def test_lvpocket_json_schemas_are_valid_draft_2020_12_documents():
    for name in ("parameters", "inputs", "outputs"):
        schema = json.loads(
            (PACKAGE_ROOT / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)


def test_golden_sample_records_public_provenance_hash_preprocessing_and_tolerances():
    metadata = json.loads(
        (PACKAGE_ROOT / "golden" / "1a26.metadata.json").read_text(encoding="utf-8")
    )
    actual_sha256 = hashlib.sha256(LEGACY_INPUT.read_bytes()).hexdigest()

    assert metadata["pdb_id"] == "1A26"
    assert metadata["source"]["url"] == "https://www.rcsb.org/structure/1A26"
    assert metadata["license"]["spdx_id"] == "CC0-1.0"
    assert metadata["input"]["sha256"] == actual_sha256
    assert metadata["input"]["sha256"] == (
        "7813fb5d8b286aed743dfde3294b5190198ea71ba29e431eff4eb99ae36a7699"
    )
    assert metadata["preprocessing"]["rules"]
    assert metadata["acceptance"]["tolerances"]
    assert metadata["validation"]["nvidia"]["status"] == "validated"
    assert metadata["validation"]["dcu"]["status"] == (
        "adapted_pending_hardware_validation"
    )


def test_result_parser_rejects_missing_result_json(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="result.json"):
        _load_result_parser().parse_result(tmp_path / "result.json", tmp_path)


def test_result_parser_rejects_path_escape(tmp_path: Path):
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "pockets": {
                    "artifact_type": "pocket_result",
                    "path": "../outside.json",
                    "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                },
                "report": {
                    "artifact_type": "run_report",
                    "path": "report.json",
                    "sha256": "0" * 64,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes output directory"):
        _load_result_parser().parse_result(result_path, tmp_path)


def test_result_parser_rejects_checksum_mismatch(tmp_path: Path):
    for name in ("pockets.json", "report.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "pockets": {
                    "artifact_type": "pocket_result",
                    "path": "pockets.json",
                    "sha256": "0" * 64,
                },
                "report": {
                    "artifact_type": "run_report",
                    "path": "report.json",
                    "sha256": hashlib.sha256(b"{}").hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        _load_result_parser().parse_result(result_path, tmp_path)


def test_legacy_entry_is_deprecated_and_points_to_reference_package():
    config = json.loads(
        (REPOSITORY_ROOT / "example" / "LVpocket" / "platform_tool.ssh_job.json").read_text(
            encoding="utf-8"
        )
    )

    assert config["deprecated"] is True
    assert config["tool_package"] == "tool-package/tool.yaml"
