"""Contract checks for the RDKit properties model-side runtime."""

from __future__ import annotations

import csv
import importlib
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "model" / "RDKitProperties"
SRC_ROOT = PACKAGE_ROOT / "src"
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.execution.result_parser import parse_standard_result  # noqa: E402
from app.execution.standard_contracts import DeclaredArtifactOutput  # noqa: E402


class FakeDescriptorBackend:
    name = "FakeRDKit"
    version = "0.0-test"

    def molecule_from_smiles(self, smiles: str):
        if smiles == "invalid":
            return None
        return {"smiles": smiles}

    def descriptors(self, molecule) -> dict[str, float | int]:
        smiles = molecule["smiles"]
        return {
            "molecular_weight": float(len(smiles) * 10),
            "logp": 1.5,
            "tpsa": 20.0,
            "hbd": 1,
            "hba": 2,
            "rotatable_bonds": 3,
            "heavy_atoms": len(smiles),
            "qed": 0.7,
            "lipinski_violations": 0,
        }


def test_rdkit_properties_runtime_calculates_table_with_injected_backend(tmp_path: Path):
    properties = importlib.import_module("rdkit_properties_runtime.properties")
    input_csv = tmp_path / "molecules.csv"
    output_csv = tmp_path / "properties.csv"
    input_csv.write_text(
        "molecule_id,SMILES\naspirin,CC(=O)OC1=CC=CC=C1C(=O)O\nbad,invalid\n",
        encoding="utf-8",
    )

    summary = properties.calculate_properties_table(
        input_csv=input_csv,
        output_csv=output_csv,
        molecule_id_field="molecule_id",
        smiles_field="SMILES",
        backend=FakeDescriptorBackend(),
    )

    rows = list(csv.DictReader(output_csv.open("r", encoding="utf-8")))
    assert summary.row_count == 2
    assert summary.valid_molecule_count == 1
    assert summary.invalid_molecule_count == 1
    assert summary.property_columns == [
        "molecular_weight",
        "logp",
        "tpsa",
        "hbd",
        "hba",
        "rotatable_bonds",
        "heavy_atoms",
        "qed",
        "lipinski_violations",
    ]
    assert rows[0]["molecular_weight"] == "240.0000"
    assert rows[0]["rdkit_status"] == "ok"
    assert rows[1]["rdkit_status"] == "invalid_smiles"


def test_rdkit_properties_runtime_builds_standard_result(tmp_path: Path):
    result_builder = importlib.import_module("rdkit_properties_runtime.result_builder")

    raw_output_dir = tmp_path / "raw"
    output_dir = tmp_path / "output"
    raw_output_dir.mkdir()
    (raw_output_dir / "rdkit_properties.csv").write_text(
        "molecule_id,SMILES,molecular_weight,rdkit_status\naspirin,CCO,30.0000,ok\n",
        encoding="utf-8",
    )

    result = result_builder.write_standard_result(
        request={
            "task": {
                "id": "task-001",
                "tool_slug": "rdkit-molecular-properties",
                "tool_version": "0.1.0",
            },
            "inputs": {"molecules": {"metadata": {"molecule_id_field": "molecule_id"}}},
        },
        raw_output_dir=raw_output_dir,
        output_dir=output_dir,
        summary={
            "row_count": 1,
            "valid_molecule_count": 1,
            "invalid_molecule_count": 0,
            "property_columns": ["molecular_weight"],
            "backend_name": "FakeRDKit",
            "backend_version": "0.0-test",
        },
    )

    assert result["result_version"] == "aidd.sciminer/result.v2"
    assert result["artifacts"]["properties"]["type"] == "molecule_table@1"
    assert set(result["artifacts"]["properties"]["files"]) == {
        "table_file",
        "metadata_json",
    }
    assert result["artifacts"]["properties"]["metadata"]["molecule_id_field"] == "molecule_id"
    assert (output_dir / "artifacts/properties/rdkit_properties.csv").is_file()
    assert (output_dir / "reports/report.json").is_file()
    assert json.loads((output_dir / "result.json").read_text(encoding="utf-8")) == result


def test_rdkit_properties_runtime_writes_standard_failure_result(tmp_path: Path):
    result_builder = importlib.import_module("rdkit_properties_runtime.result_builder")
    output_dir = tmp_path / "output"

    result_builder.write_failure_result(output_dir=output_dir, error=RuntimeError("missing RDKit"))

    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert result["result_version"] == "aidd.sciminer/result.v2"
    assert result["summary"]["status"] == "failed"
    assert result["artifacts"]["report"]["type"] == "run_report@1"

    parsed = parse_standard_result(
        result_path=output_dir / "result.json",
        output_dir=output_dir,
        declared_outputs=[DeclaredArtifactOutput(name="report", type="run_report@1")],
    )
    assert parsed.artifacts[0].output_name == "report"


def test_rdkit_properties_platform_run_is_thin_cli_delegate():
    script = (PACKAGE_ROOT / "platform_run.sh").read_text(encoding="utf-8")

    assert "rdkit_properties_runtime.cli" in script
    assert "cat >" not in script
    assert "/home/" not in script
    assert "/data/" not in script
    assert "/workspace/" not in script


def test_rdkit_properties_platform_run_accepts_model_root_argument():
    result = subprocess.run(
        [
            "bash",
            str(PACKAGE_ROOT / "platform_run.sh"),
            "--model-root",
            str(PACKAGE_ROOT),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Missing required arguments" in result.stderr
    assert "Unknown argument" not in result.stderr
