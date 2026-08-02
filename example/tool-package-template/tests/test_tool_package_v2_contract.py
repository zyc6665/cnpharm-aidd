"""Self-tests that package authors should keep with every Tool Package v2 package."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tool_packages.loader import load_tool_package  # noqa: E402
from app.tool_packages.schemas import ToolPackageV2Manifest  # noqa: E402
from app.tool_packages.validator import validate_tool_package  # noqa: E402


def test_template_loads_as_tool_package_v2_manifest():
    manifest = load_tool_package(PACKAGE_ROOT)
    result = validate_tool_package(manifest)

    assert isinstance(manifest, ToolPackageV2Manifest)
    assert result.is_valid is True, result.errors
    assert [(item.name, item.type) for item in manifest.artifacts.inputs] == [
        ("protein", "protein_structure@1")
    ]
    assert [(item.name, item.type, item.cardinality) for item in manifest.artifacts.outputs] == [
        ("pocket", "binding_pocket@1", "one"),
        ("report", "run_report@1", "one"),
    ]


def test_example_request_is_standard_request_v1():
    request = json.loads((PACKAGE_ROOT / "examples" / "request.json").read_text(encoding="utf-8"))
    schema = json.loads(
        (PACKAGE_ROOT / "schemas" / "parameters.schema.json").read_text(encoding="utf-8")
    )

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(request["parameters"])
    assert request["request_version"] == "aidd.sciminer/request.v1"
    assert request["inputs"]["protein"]["type"] == "protein_structure@1"


def test_runner_delegates_to_model_side_package():
    entrypoint = (PACKAGE_ROOT / "runner" / "entrypoint.sh").read_text(encoding="utf-8")

    assert "MODEL_PACKAGE_ROOT" in entrypoint
    assert "platform_run.sh" in entrypoint
    assert "runner.tool_impl" not in entrypoint
    assert "runner.result_parser" not in entrypoint


def test_template_does_not_keep_legacy_v1_authoring_files():
    stale = [
        "schemas/inputs.schema.json",
        "schemas/outputs.schema.json",
        "runner/tool_impl.py",
        "runner/result_parser.py",
    ]

    assert [path for path in stale if (PACKAGE_ROOT / path).exists()] == []


def test_template_does_not_embed_secret_ip_or_host_path():
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
