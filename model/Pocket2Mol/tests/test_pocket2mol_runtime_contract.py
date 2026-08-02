"""Model-side contract tests for the Pocket2Mol runtime package."""

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
        "src/pocket2mol_runtime/__init__.py",
        "src/pocket2mol_runtime/cli.py",
        "src/pocket2mol_runtime/io.py",
        "src/pocket2mol_runtime/result_builder.py",
    }
    missing = sorted(path for path in required_files if not (PACKAGE_ROOT / path).is_file())

    assert missing == []


def test_model_package_metadata_uses_platform_standard_contracts():
    import yaml

    metadata = yaml.safe_load((PACKAGE_ROOT / "MODEL_PACKAGE.yaml").read_text(encoding="utf-8"))

    assert metadata["slug"] == "pocket2mol-pocket-ligand-generation"
    assert metadata["entrypoint"] == "platform_run.sh"
    assert metadata["runtime"]["python"] == "3.10"
    assert metadata["model_code"]["wrapper_package"] == "src/pocket2mol_runtime"
    assert metadata["standard_contract"]["inputs"] == [
        {"name": "pocket", "type": "binding_pocket@1"}
    ]
    assert metadata["standard_contract"]["outputs"] == [
        {"name": "molecules", "type": "molecule_table@1"},
        {"name": "ligands", "type": "ligand_structure@1"},
        {"name": "report", "type": "run_report@1"},
    ]
    assert "/home/" not in json.dumps(metadata)
    assert "/data/" not in json.dumps(metadata)


def test_result_builder_wraps_legacy_pocket2mol_outputs_as_result_v2(tmp_path: Path):
    result_builder = importlib.import_module("pocket2mol_runtime.result_builder")

    raw_output_dir = tmp_path / "raw"
    output_dir = tmp_path / "output"
    artifact_dir = raw_output_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "generated_molecules.sdf").write_text(
        "ligand_001\n  SciMiner\n\n  0  0  0  0  0  0            999 V2000\nM  END\n$$$$\n",
        encoding="utf-8",
    )
    (artifact_dir / "molecules.csv").write_text(
        "molecule_id,smiles,rank\nligand_001,CCO,1\n",
        encoding="utf-8",
    )

    result = result_builder.write_standard_result(
        request={
            "task": {
                "id": "task-001",
                "tool_slug": "pocket2mol-pocket-ligand-generation",
                "tool_version": "0.1.2",
            }
        },
        raw_output_dir=raw_output_dir,
        output_dir=output_dir,
    )

    assert result["result_version"] == "aidd.sciminer/result.v2"
    assert result["artifacts"]["molecules"]["type"] == "molecule_table@1"
    assert result["artifacts"]["ligands"][0]["type"] == "ligand_structure@1"
    assert (output_dir / "artifacts/molecules/molecules.csv").is_file()
    assert (output_dir / "artifacts/ligands/ligand_001.sdf").is_file()
    assert (output_dir / "reports/report.json").is_file()


def test_cli_builds_legacy_params_from_standard_binding_pocket_request(tmp_path: Path):
    cli = importlib.import_module("pocket2mol_runtime.cli")

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    staged_pocket = input_dir / "pocket" / "atom_pocket_pdb.pdb"
    staged_pocket.parent.mkdir()
    staged_pocket.write_text("HETATM\nEND\n", encoding="utf-8")

    request = {
        "request_version": "aidd.sciminer/request.v1",
        "task": {
            "id": "task-001",
            "tool_slug": "pocket2mol-pocket-ligand-generation",
            "tool_version": "0.1.2",
        },
        "inputs": {
            "pocket": {
                "artifact_version_id": "version-1",
                "type": "binding_pocket@1",
                "files": {
                    "atom_pocket_pdb": {
                        "path": "input/pocket/atom_pocket_pdb.pdb",
                        "sha256": "0" * 64,
                    }
                },
                "metadata": {"center": [1.0, 2.0, 3.0]},
            }
        },
        "parameters": {"num_samples": 2},
        "execution": {"variant": "cpu", "accelerator": "cpu"},
    }

    legacy_params = cli.build_legacy_payload(request, input_dir=input_dir)

    assert legacy_params["task_name"] == "pocket2mol_pdb_sampling"
    assert legacy_params["params"]["num_samples"] == 2
    assert legacy_params["params"]["center"] == "1.0,2.0,3.0"
    assert legacy_params["input_files"]["protein_pdb"] == "pocket/atom_pocket_pdb.pdb"


def test_platform_run_delegates_to_runtime_cli_without_embedded_adapter_code():
    script = (PACKAGE_ROOT / "platform_run.sh").read_text(encoding="utf-8")

    assert "pocket2mol_runtime.cli" in script
    assert "cat >" not in script
    assert "/home/" not in script
    assert "/data/" not in script
