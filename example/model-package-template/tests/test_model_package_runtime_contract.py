"""Package-local checks for copied model package templates."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def test_template_runtime_wraps_predictions_as_result_v2(tmp_path: Path):
    result_builder = importlib.import_module("model_runtime_template.result_builder")
    raw_output_dir = tmp_path / "raw"
    output_dir = tmp_path / "output"
    raw_output_dir.mkdir()
    (raw_output_dir / "predictions.csv").write_text(
        "molecule_id,score\nmol-1,0.9\n",
        encoding="utf-8",
    )

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

    assert result["result_version"] == "aidd.sciminer/result"
    assert result["artifacts"]["properties"]["type"] == "molecule_table@1"
    assert set(result["artifacts"]["properties"]["files"]) == {"table_file", "metadata_json"}
    assert json.loads((output_dir / "result.json").read_text(encoding="utf-8")) == result
