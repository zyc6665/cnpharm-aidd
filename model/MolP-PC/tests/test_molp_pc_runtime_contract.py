"""Model-side contract tests for the standardized MolP-PC package."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def test_model_package_declares_standard_layout_and_ignores_runtime_artifacts():
    required_files = {
        ".gitignore",
        "MODEL_PACKAGE.yaml",
        "MODEL_PACKAGE_GUIDE.md",
        "README.md",
        "platform_run.sh",
        "src/molp_pc_runtime/__init__.py",
        "src/molp_pc_runtime/cli.py",
        "src/molp_pc_runtime/contracts.py",
        "src/molp_pc_runtime/csv_contract.py",
        "src/molp_pc_runtime/io.py",
        "src/molp_pc_runtime/legacy_predict.py",
        "src/molp_pc_runtime/result_builder.py",
        "predict/model/WEIGHTS.md",
        "wheelhouse/README.md",
    }
    missing = sorted(path for path in required_files if not (PACKAGE_ROOT / path).is_file())

    assert missing == []

    ignore_rules = (PACKAGE_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (
        "predict/model/*.pth",
        "wheelhouse/*.whl",
        "platform_tool.ssh_job.json",
        "CLEANUP_REMOVED_PATH.txt",
        "predict/cb_data_fine.csv",
    ):
        assert pattern in ignore_rules


def test_model_package_metadata_uses_platform_standard_contracts():
    import yaml

    metadata = yaml.safe_load((PACKAGE_ROOT / "MODEL_PACKAGE.yaml").read_text(encoding="utf-8"))
    runtime = metadata["runtime"]

    assert metadata["slug"] == "molp-pc-property-prediction"
    assert metadata["version"] == "0.1.1"
    assert metadata["entrypoint"] == "platform_run.sh"
    assert runtime["python"] == "3.8"
    assert runtime["cuda"] == "11.3"
    assert runtime["artifacts"]["primary"]["kind"] == "container"
    assert runtime["artifacts"]["fallback"]["kind"] == "conda_pack"
    assert set(runtime["executor_support"]) == {"ssh_docker_exec", "slurm", "k8s_job"}
    assert "digest" in runtime["selection_policy"]
    assert runtime["cache_policy"]["mutable_host_paths_forbidden"] is True
    assert metadata["standard_contract"]["inputs"] == [
        {"name": "molecules", "type": "molecule_table@1"}
    ]
    assert metadata["standard_contract"]["outputs"] == [
        {"name": "properties", "type": "molecule_table@1"},
        {"name": "report", "type": "run_report@1"},
    ]
    assert "/home/" not in json.dumps(metadata)
    assert "/data/" not in json.dumps(metadata)


def test_csv_contract_validates_smiles_tables_and_prediction_tables(tmp_path: Path):
    csv_contract = importlib.import_module("molp_pc_runtime.csv_contract")

    input_csv = tmp_path / "smiles.csv"
    input_csv.write_text("SMILES\nCCO\nc1ccccc1\n", encoding="utf-8")
    prediction_csv = tmp_path / "predictions.csv"
    prediction_csv.write_text("SMILES,F20,LD50_zhu\nCCO,0.9,1.4\n", encoding="utf-8")

    input_summary = csv_contract.inspect_molecule_table(input_csv)
    prediction_summary = csv_contract.inspect_prediction_table(prediction_csv)

    assert input_summary.row_count == 2
    assert input_summary.molecule_id_field == "SMILES"
    assert prediction_summary.row_count == 1
    assert prediction_summary.property_columns == ["F20", "LD50_zhu"]


def test_result_builder_wraps_legacy_output_as_standard_result_v2(tmp_path: Path):
    result_builder = importlib.import_module("molp_pc_runtime.result_builder")

    raw_output_dir = tmp_path / "raw"
    output_dir = tmp_path / "output"
    raw_output_dir.mkdir()
    (raw_output_dir / "cb_data_result.csv").write_text("SMILES,F20\nCCO,0.9\n", encoding="utf-8")

    result = result_builder.write_standard_result(
        request={
            "task": {
                "id": "task-001",
                "tool_slug": "molp-pc-property-prediction",
                "tool_version": "0.1.1",
            },
            "inputs": {
                "molecules": {
                    "metadata": {"molecule_id_field": "SMILES"},
                }
            },
        },
        raw_output_dir=raw_output_dir,
        output_dir=output_dir,
    )

    assert result["result_version"] == "aidd.sciminer/result.v2"
    assert result["artifacts"]["properties"]["type"] == "molecule_table@1"
    assert set(result["artifacts"]["properties"]["files"]) == {"table_file", "metadata_json"}
    metadata = result["artifacts"]["properties"]["metadata"]
    assert metadata["model_name"] == "MolP-PC"
    assert metadata["model_version"] == "0.1.1"
    assert metadata["endpoint_ref"] == "local_runtime:molp-pc-property-prediction@0.1.1"
    assert metadata["evidence_level"] == "engineering_smoke_only"
    assert metadata["applicability_domain_status"] == "unknown"
    assert metadata["unit_or_label_policy"] == "per_endpoint_definition_or_unknown"
    assert metadata["model_card_ref"] == "docs/model-card.md"
    assert metadata["verification_record_ref"] == "docs/verification-record.md"
    report = json.loads((output_dir / "reports/report.json").read_text(encoding="utf-8"))
    assert report["scientific_interpretation"] == {
        key: metadata[key]
        for key in [
            "model_name",
            "model_version",
            "runtime_ref",
            "weights_ref",
            "endpoint_ref",
            "evidence_level",
            "applicability_domain_status",
            "unit_or_label_policy",
            "model_card_ref",
            "verification_record_ref",
        ]
    } | {"prediction_kind": "basic_admet_prediction"}
    assert (output_dir / "artifacts/properties/molp_pc_predictions.csv").is_file()
    assert (output_dir / "artifacts/properties/metadata.json").is_file()
    assert (output_dir / "reports/report.json").is_file()
    assert json.loads((output_dir / "result.json").read_text(encoding="utf-8")) == result


def test_result_builder_accepts_legacy_artifacts_prediction_csv(tmp_path: Path):
    result_builder = importlib.import_module("molp_pc_runtime.result_builder")

    raw_output_dir = tmp_path / "raw"
    output_dir = tmp_path / "output"
    artifact_dir = raw_output_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "cb_data_result.csv").write_text(
        "SMILES,F20\nCCO,0.9\n",
        encoding="utf-8",
    )

    result = result_builder.write_standard_result(
        request={
            "task": {
                "id": "task-001",
                "tool_slug": "molp-pc-property-prediction",
                "tool_version": "0.1.1",
            }
        },
        raw_output_dir=raw_output_dir,
        output_dir=output_dir,
    )

    assert result["artifacts"]["properties"]["metadata"]["row_count"] == 1


def test_platform_run_delegates_to_runtime_cli_without_embedded_python():
    script = (PACKAGE_ROOT / "platform_run.sh").read_text(encoding="utf-8")

    assert "molp_pc_runtime.cli" in script
    assert "cat >" not in script
    assert "/home/" not in script
    assert "/data/" not in script
    assert "/workspace/" not in script
