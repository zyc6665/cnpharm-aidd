"""Contract checks for the reusable model-side package template."""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = PROJECT_ROOT / "example" / "model-package-template"
SRC_ROOT = TEMPLATE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


REQUIRED_FILES = {
    ".gitignore",
    "AGENTS.md",
    "MODEL_PACKAGE.yaml",
    "MODEL_PACKAGE_GUIDE.md",
    "MODEL_SIDE_PLATFORMIZATION_PROMPT.md",
    "README.md",
    "environment.yml",
    "requirements.txt",
    "platform_run.sh",
    "examples/request.legacy.json",
    "examples/request.standard.json",
    "examples/sample_input/molecules.csv",
    "examples/sample_output/predictions.csv",
    "original_model/README.md",
    "original_model/inference.py",
    "weights/WEIGHTS.md",
    "wheelhouse/README.md",
    "src/model_runtime_template/__init__.py",
    "src/model_runtime_template/cli.py",
    "src/model_runtime_template/contracts.py",
    "src/model_runtime_template/csv_contract.py",
    "src/model_runtime_template/io.py",
    "src/model_runtime_template/legacy_predict.py",
    "src/model_runtime_template/result_builder.py",
    "tests/test_model_package_runtime_contract.py",
}


def test_model_package_template_contains_standard_authoring_files():
    missing = sorted(path for path in REQUIRED_FILES if not (TEMPLATE_ROOT / path).is_file())

    assert missing == []


def test_model_package_template_metadata_declares_model_side_contract():
    import yaml

    metadata = yaml.safe_load((TEMPLATE_ROOT / "MODEL_PACKAGE.yaml").read_text(encoding="utf-8"))
    runtime = metadata["runtime"]

    assert metadata["schema_version"] == "sciminer.model-package.v1"
    assert metadata["entrypoint"] == "platform_run.sh"
    assert runtime["python"] == "3.10"
    assert runtime["artifacts"]["primary"]["kind"] == "container"
    assert runtime["artifacts"]["fallback"]["kind"] == "conda_pack"
    assert set(runtime["executor_support"]) == {"ssh_docker_exec", "slurm", "k8s_job"}
    assert "digest" in runtime["selection_policy"]
    assert runtime["cache_policy"]["mutable_host_paths_forbidden"] is True
    assert metadata["model_code"]["source_dir"] == "original_model"
    assert metadata["model_code"]["wrapper_package"] == "src/model_runtime_template"
    assert metadata["standard_contract"]["inputs"] == [
        {"name": "molecules", "type": "molecule_table@1"}
    ]
    assert metadata["standard_contract"]["outputs"] == [
        {"name": "properties", "type": "molecule_table@1"},
        {"name": "report", "type": "run_report@1"},
    ]


def test_model_package_template_runtime_builds_standard_result(tmp_path: Path):
    result_builder = importlib.import_module("model_runtime_template.result_builder")

    raw_output_dir = tmp_path / "raw"
    output_dir = tmp_path / "output"
    raw_output_dir.mkdir()
    (raw_output_dir / "predictions.csv").write_text("molecule_id,score\nmol-1,0.9\n", encoding="utf-8")

    result = result_builder.write_standard_result(
        request={
            "task": {
                "id": "task-001",
                "tool_slug": "example-model-package-template",
                "tool_version": "0.1.0",
            },
            "inputs": {"molecules": {"metadata": {"molecule_id_field": "molecule_id"}}},
        },
        raw_output_dir=raw_output_dir,
        output_dir=output_dir,
    )

    assert result["result_version"] == "aidd.sciminer/result.v2"
    assert result["artifacts"]["properties"]["type"] == "molecule_table@1"
    assert set(result["artifacts"]["properties"]["files"]) == {"table_file", "metadata_json"}
    assert result["artifacts"]["properties"]["metadata"]["molecule_id_field"] == "molecule_id"
    assert (output_dir / "artifacts/properties/predictions.csv").is_file()
    assert (output_dir / "reports/report.json").is_file()
    assert json.loads((output_dir / "result.json").read_text(encoding="utf-8")) == result


def test_model_package_template_platform_run_is_thin_cli_delegate():
    script = (TEMPLATE_ROOT / "platform_run.sh").read_text(encoding="utf-8")

    assert "model_runtime_template.cli" in script
    assert "cat >" not in script
    assert "/home/" not in script
    assert "/data/" not in script
    assert "/workspace/" not in script


def test_model_package_template_ignores_large_and_machine_specific_artifacts():
    ignore_rules = (TEMPLATE_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (
        "weights/*",
        "!weights/WEIGHTS.md",
        "wheelhouse/*.whl",
        "deployment.local.*",
        "platform_tool.ssh_job.json",
        "output/",
        "work/",
    ):
        assert pattern in ignore_rules


def test_model_package_template_prompt_tells_agents_not_to_change_platform():
    prompt = (TEMPLATE_ROOT / "MODEL_SIDE_PLATFORMIZATION_PROMPT.md").read_text(
        encoding="utf-8"
    )
    guide = (TEMPLATE_ROOT / "MODEL_PACKAGE_GUIDE.md").read_text(encoding="utf-8")
    runtime_doc = (PROJECT_ROOT / "docs/guides/model-runtime-packaging.md").read_text(
        encoding="utf-8"
    )

    combined = f"{prompt}\n{guide}\n{runtime_doc}"
    assert "平台契约固定" in combined
    assert "不要修改平台后端或前端" in combined
    assert "MODEL_PACKAGE.yaml" in combined
    assert "platform_run.sh" in combined
    assert "result.v2" in combined
    assert "Runtime Env" in combined
    assert "container" in combined
    assert "conda-pack" in combined
    assert "镜像 digest" in combined
    assert "Executor 不安装依赖" in combined


def test_model_package_template_has_no_secrets_or_host_paths():
    text_suffixes = {"", ".json", ".md", ".py", ".sh", ".yaml", ".yml", ".txt", ".csv"}
    content = "\n".join(
        path.read_text(encoding="utf-8")
        for path in TEMPLATE_ROOT.rglob("*")
        if path.is_file() and path.suffix in text_suffixes
    )

    secret_assignment = r"(?i)(password|secret|access[_-]?key)\s*[:=]\s*[^${<\s][^\s]*"
    assert not re.search(secret_assignment, content)
    assert not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", content)
    assert not re.search(r"(?m)(?:^|[\s:'\"])/(?:home|root|data|mnt|opt|srv|workspace)/", content)
