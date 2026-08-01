"""Package-local checks for the MolP-PC platform adapter."""

from __future__ import annotations

import importlib.util
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _load_adapter():
    path = PACKAGE_ROOT / "runner" / "platform_adapter.py"
    spec = importlib.util.spec_from_file_location("molp_pc_platform_adapter", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_adapter_emits_molecule_table_result_from_prediction_csv(tmp_path: Path):
    raw_dir = tmp_path / "legacy-output"
    output_dir = tmp_path / "output"
    raw_dir.mkdir()
    (raw_dir / "cb_data_result.csv").write_text("SMILES,F20\nCCO,0.9\n", encoding="utf-8")

    result = _load_adapter().adapt_legacy_outputs(
        request={
            "task": {
                "id": "task-001",
                "tool_slug": "molp-pc-property-prediction",
                "tool_version": "0.1.0",
            }
        },
        raw_output_dir=raw_dir,
        output_dir=output_dir,
    )

    assert result["result_version"] == "aidd.sciminer/result.v2"
    assert result["artifacts"]["properties"]["type"] == "molecule_table@1"
    assert set(result["artifacts"]["properties"]["files"]) == {"table_file", "metadata_json"}
    assert result["artifacts"]["properties"]["metadata"]["molecule_id_field"] == "SMILES"
    assert (output_dir / "artifacts/properties/molp_pc_predictions.csv").is_file()
