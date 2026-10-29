"""Production contract checks for the AI-assisted Tool Package template."""

from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from app.tool_packages.loader import load_tool_package
from app.tool_packages.schemas import ToolPackageManifest
from app.tool_packages.validator import validate_tool_package


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = REPOSITORY_ROOT / "example" / "tool-package-template"
REQUIRED_FILES = {
    "tool.yaml",
    "schemas/parameters.schema.json",
    "variants/cpu.yaml",
    "variants/nvidia-cuda.yaml",
    "variants/haiguang-dcu.yaml",
    "runner/entrypoint.sh",
    "tests/test_tool_package_v2_contract.py",
    "AGENTS.md",
}


def test_template_contains_required_authoring_files():
    missing = sorted(path for path in REQUIRED_FILES if not (TEMPLATE_ROOT / path).is_file())

    assert missing == []


def test_template_does_not_keep_legacy_v1_authoring_files():
    stale = [
        "schemas/inputs.schema.json",
        "schemas/outputs.schema.json",
        "runner/tool_impl.py",
        "runner/result_parser.py",
    ]

    assert [path for path in stale if (TEMPLATE_ROOT / path).exists()] == []


def test_template_loads_with_the_production_validator():
    package = load_tool_package(TEMPLATE_ROOT)
    result = validate_tool_package(package)

    assert isinstance(package, ToolPackageManifest)
    assert result.is_valid is True, result.errors
    assert [(item.name, item.type) for item in package.artifacts.inputs] == [
        ("protein", "protein_structure@1")
    ]
    assert [(item.name, item.type, item.cardinality) for item in package.artifacts.outputs] == [
        ("pocket", "binding_pocket@1", "one"),
        ("report", "run_report@1", "one"),
    ]


def test_template_example_request_matches_parameter_schema():
    request = json.loads((TEMPLATE_ROOT / "examples" / "request.json").read_text(encoding="utf-8"))

    schema = json.loads(
        (TEMPLATE_ROOT / "schemas" / "parameters.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(request["parameters"])
    assert request["request_version"] == "aidd.sciminer/request"
    assert request["inputs"]["protein"]["type"] == "protein_structure@1"


def test_variants_share_outputs_and_report_hardware_truthfully():
    package = load_tool_package(TEMPLATE_ROOT)
    variants = {variant.accelerator.value: variant for variant in package.variants}

    assert set(variants) == {"cpu", "nvidia_cuda", "haiguang_dcu"}
    assert {tuple(variant.entrypoint) for variant in variants.values()} == {
        ("runner/entrypoint.sh",)
    }
    assert variants["cpu"].validation_status.value == "unvalidated"
    assert variants["nvidia_cuda"].validation_status.value == "unvalidated"
    assert variants["nvidia_cuda"].resources.devices
    assert variants["nvidia_cuda"].resources.driver
    assert (
        variants["haiguang_dcu"].validation_status.value
        == "adapted_pending_hardware_validation"
    )


def test_template_does_not_embed_secret_ip_or_host_path():
    text_suffixes = {"", ".json", ".md", ".py", ".sh", ".yaml", ".yml"}
    content = "\n".join(
        path.read_text(encoding="utf-8")
        for path in TEMPLATE_ROOT.rglob("*")
        if path.is_file() and path.suffix in text_suffixes
    )

    secret_assignment = r"(?i)(password|secret|access[_-]?key)\s*[:=]\s*[^${<\s][^\s]*"
    assert not re.search(secret_assignment, content)
    assert not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", content)
    assert not re.search(r"(?m)(?:^|[\s:'\"])/(?:home|root|data|mnt|opt|srv)/", content)
