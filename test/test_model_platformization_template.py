"""Contract checks for the reusable model platformization template."""

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


TEMPLATE_ROOT = PROJECT_ROOT / "example" / "model-platformization-template"
REQUIRED_FILES = {
    "tool.yaml",
    "README.md",
    "AGENTS.md",
    "MODEL_PLATFORMIZATION_PROMPT.md",
    "examples/request.json",
    "examples/output/result.json",
    "examples/output/artifacts/pocket/residue_pocket.pdb",
    "examples/output/artifacts/pocket/atom_pocket.pdb",
    "examples/output/artifacts/pocket/pocket_metadata.json",
    "examples/output/reports/report.json",
    "runner/entrypoint.sh",
    "schemas/parameters.schema.json",
    "schemas/result.v2.example.json",
    "tests/test_model_platformization_contract.py",
}


def test_platformization_template_contains_agent_handoff_files():
    missing = sorted(path for path in REQUIRED_FILES if not (TEMPLATE_ROOT / path).is_file())

    assert missing == []


def test_platformization_template_loads_as_standard_v2_manifest():
    manifest = load_tool_package(TEMPLATE_ROOT)
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


def test_platformization_template_result_matches_standard_binding_pocket_contract():
    parsed = parse_standard_result(
        result_path=TEMPLATE_ROOT / "schemas" / "result.v2.example.json",
        output_dir=TEMPLATE_ROOT / "examples" / "output",
        declared_outputs=[
            DeclaredArtifactOutput(name="pocket", type="binding_pocket@1"),
            DeclaredArtifactOutput(name="report", type="run_report@1", required=False),
        ],
    )

    pocket = next(artifact for artifact in parsed.artifacts if artifact.output_name == "pocket")

    assert set(pocket.files) == {
        "residue_pocket_pdb",
        "atom_pocket_pdb",
        "pocket_metadata_json",
    }
    assert pocket.metadata["source_protein_ref"] == "input:protein"


def test_platformization_template_prompt_keeps_platform_contract_fixed():
    prompt = (TEMPLATE_ROOT / "MODEL_PLATFORMIZATION_PROMPT.md").read_text(encoding="utf-8")
    readme = (TEMPLATE_ROOT / "README.md").read_text(encoding="utf-8")

    combined = f"{prompt}\n{readme}"
    assert "平台契约固定" in combined
    assert "不要修改平台后端或前端" in combined
    assert "binding_pocket@1" in combined
    assert "residue_pocket_pdb" in combined
    assert "atom_pocket_pdb" in combined
    assert "Runtime Env" in combined
    assert "镜像 digest" in combined
    assert "Executor 不安装依赖" in combined


def test_platformization_template_keeps_adapter_on_model_side():
    prompt = (TEMPLATE_ROOT / "MODEL_PLATFORMIZATION_PROMPT.md").read_text(encoding="utf-8")
    readme = (TEMPLATE_ROOT / "README.md").read_text(encoding="utf-8")
    entrypoint = (TEMPLATE_ROOT / "runner" / "entrypoint.sh").read_text(encoding="utf-8")

    assert not (TEMPLATE_ROOT / "runner" / "platform_adapter.py").exists()
    assert "runner/platform_adapter.py" not in prompt
    assert "runner/platform_adapter.py" not in readme
    assert "model/<Model>/src/<runtime>" in prompt
    assert "model/<Model>/src/<runtime>" in readme
    assert "MODEL_PACKAGE_ROOT" in entrypoint
    assert "platform_run.sh" in entrypoint
    assert "python3 \"${SCRIPT_DIR}/platform_adapter.py\"" not in entrypoint


def test_platformization_template_does_not_embed_secrets_or_host_paths():
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
