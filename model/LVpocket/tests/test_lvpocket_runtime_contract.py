"""Model-side contract tests for the LVpocket runtime package."""

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
        "src/lvpocket_runtime/__init__.py",
        "src/lvpocket_runtime/cli.py",
        "src/lvpocket_runtime/io.py",
        "src/lvpocket_runtime/result_builder.py",
    }
    missing = sorted(path for path in required_files if not (PACKAGE_ROOT / path).is_file())

    assert missing == []


def test_model_package_metadata_uses_platform_standard_contracts():
    import yaml

    metadata = yaml.safe_load((PACKAGE_ROOT / "MODEL_PACKAGE.yaml").read_text(encoding="utf-8"))

    assert metadata["slug"] == "lvpocket-standard-pocket"
    assert metadata["entrypoint"] == "platform_run.sh"
    assert metadata["model_code"]["wrapper_package"] == "src/lvpocket_runtime"
    assert metadata["standard_contract"]["inputs"] == [
        {"name": "protein", "type": "protein_structure@1"}
    ]
    assert metadata["standard_contract"]["outputs"] == [
        {"name": "pocket", "type": "binding_pocket@1"},
        {"name": "report", "type": "run_report@1"},
    ]
    assert "/home/" not in json.dumps(metadata)
    assert "/data/" not in json.dumps(metadata)


def test_result_builder_wraps_legacy_output_as_standard_result_v2(tmp_path: Path):
    result_builder = importlib.import_module("lvpocket_runtime.result_builder")

    raw_output_dir = tmp_path / "raw"
    artifact_dir = raw_output_dir / "artifacts"
    output_dir = tmp_path / "output"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "pocket0.pdb").write_text(
        "ATOM      1  C   LIG A   1      11.104  13.207   9.245  1.00 20.00           C\n",
        encoding="utf-8",
    )
    (artifact_dir / "protein_pocket_residues.pdb").write_text(
        "ATOM      1  CA  ALA A  10      11.832  13.224   9.338  1.00 20.00           C\n",
        encoding="utf-8",
    )
    (raw_output_dir / "prediction.json").write_text(
        json.dumps({"center": [11.832, 13.224, 9.338], "distance_cutoff": 8.0}),
        encoding="utf-8",
    )

    result = result_builder.write_standard_result(
        request={
            "task": {
                "id": "task-001",
                "tool_slug": "lvpocket-standard-pocket",
                "tool_version": "1.0.0",
            }
        },
        raw_output_dir=raw_output_dir,
        output_dir=output_dir,
    )

    assert result["result_version"] == "aidd.sciminer/result.v2"
    assert result["artifacts"]["pocket"]["type"] == "binding_pocket@1"
    assert set(result["artifacts"]["pocket"]["files"]) == {
        "residue_pocket_pdb",
        "atom_pocket_pdb",
        "pocket_metadata_json",
    }
    assert (output_dir / "result.json").is_file()


def test_result_builder_accepts_lvpocket_lv_results_layout(tmp_path: Path):
    result_builder = importlib.import_module("lvpocket_runtime.result_builder")

    raw_output_dir = tmp_path / "raw"
    legacy_dir = raw_output_dir / "artifacts" / "lv_results" / "input"
    output_dir = tmp_path / "output"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "pocket0.pdb").write_text(
        "ATOM      1  C   LIG A   1      11.104  13.207   9.245  1.00 20.00           C\n",
        encoding="utf-8",
    )
    (legacy_dir / "protein_pocket_residues.pdb").write_text(
        "ATOM      1  CA  ALA A  10      11.832  13.224   9.338  1.00 20.00           C\n",
        encoding="utf-8",
    )
    (raw_output_dir / "result.json").write_text(
        json.dumps(
            {
                "success": True,
                "outputs": {
                    "pockets": [{"id": "pocket0", "pdb": "artifacts/lv_results/input/pocket0.pdb"}],
                    "protein_pocket_residues": {
                        "path": "artifacts/lv_results/input/protein_pocket_residues.pdb",
                        "residue_count": 96,
                        "atom_count": 759,
                        "distance_cutoff": 8.0,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    result = result_builder.write_standard_result(
        request={"task": {"id": "task-002"}},
        raw_output_dir=raw_output_dir,
        output_dir=output_dir,
    )

    metadata = result["artifacts"]["pocket"]["metadata"]
    assert metadata["residue_count"] == 96
    assert metadata["atom_count"] == 759
    assert metadata["distance_cutoff_angstrom"] == 8.0


def test_platform_run_delegates_to_runtime_cli_without_embedded_adapter_code():
    script = (PACKAGE_ROOT / "platform_run.sh").read_text(encoding="utf-8")

    assert "lvpocket_runtime.cli" in script
    assert "cat >" not in script
    assert "/home/" not in script
    assert "/data/" not in script
