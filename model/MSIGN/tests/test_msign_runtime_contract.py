"""Model-side contract tests for the MSIGN runtime package."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def test_model_package_declares_standard_layout():
    required_files = {
        ".gitignore",
        "MODEL_PACKAGE.yaml",
        "README.md",
        "platform_run.sh",
        "src/msign_runtime/__init__.py",
        "src/msign_runtime/cli.py",
        "src/msign_runtime/io.py",
        "src/msign_runtime/result_builder.py",
    }
    missing = sorted(path for path in required_files if not (PACKAGE_ROOT / path).is_file())

    assert missing == []


def test_model_package_metadata_uses_platform_standard_contracts():
    import yaml

    metadata = yaml.safe_load((PACKAGE_ROOT / "MODEL_PACKAGE.yaml").read_text(encoding="utf-8"))

    assert metadata["slug"] == "msign-affinity-prediction"
    assert metadata["entrypoint"] == "platform_run.sh"
    assert metadata["runtime"]["python"] == "3.9"
    assert metadata["model_code"]["wrapper_package"] == "src/msign_runtime"
    assert metadata["standard_contract"]["inputs"] == [
        {"name": "protein", "type": "protein_structure@1"},
        {"name": "ligand", "type": "ligand_structure@1"},
    ]
    assert metadata["standard_contract"]["outputs"] == [
        {"name": "affinity", "type": "molecule_table@1"},
        {"name": "report", "type": "run_report@1"},
    ]
    assert "/home/" not in json.dumps(metadata)
    assert "/data/" not in json.dumps(metadata)


def test_result_builder_wraps_legacy_output_as_standard_result_v2(tmp_path: Path):
    result_builder = importlib.import_module("msign_runtime.result_builder")

    raw_output_dir = tmp_path / "raw"
    output_dir = tmp_path / "output"
    raw_output_dir.mkdir()
    (raw_output_dir / "result.json").write_text(
        json.dumps(
            {
                "success": True,
                "outputs": {
                    "complex_id": "molecule_1",
                    "prediction": {
                        "predicted_affinity": -8.1,
                        "predicted_ligand_to_pocket": -7.9,
                        "predicted_pocket_to_ligand": -8.3,
                        "scale": "pK",
                    },
                    "model_name": "full_finetune",
                    "device": "cpu",
                    "distance_angstrom": 5.0,
                },
            }
        ),
        encoding="utf-8",
    )

    result = result_builder.write_standard_result(
        request={
            "task": {
                "id": "task-001",
                "tool_slug": "msign-affinity-prediction",
                "tool_version": "0.1.1",
            }
        },
        raw_output_dir=raw_output_dir,
        output_dir=output_dir,
    )

    assert result["result_version"] == "aidd.sciminer/result.v2"
    assert result["artifacts"]["affinity"]["type"] == "molecule_table@1"
    assert set(result["artifacts"]["affinity"]["files"]) == {"table_file", "metadata_json"}
    assert "predicted_affinity" in (
        output_dir / "artifacts/affinity/msign_affinity.csv"
    ).read_text(encoding="utf-8")


def test_platform_run_delegates_to_runtime_cli_without_embedded_adapter_code():
    script = (PACKAGE_ROOT / "platform_run.sh").read_text(encoding="utf-8")

    assert "msign_runtime.cli" in script
    assert "cat >" not in script
    assert "/home/" not in script
    assert "/data/" not in script
