"""Package-local checks for copied model platformization templates."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _load_adapter():
    path = PACKAGE_ROOT / "runner" / "platform_adapter.py"
    spec = importlib.util.spec_from_file_location("platform_adapter", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_adapter_emits_result_v2_from_standard_pocket_files(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "output"
    raw_dir.mkdir()
    (raw_dir / "residue_pocket.pdb").write_text("ATOM\nEND\n", encoding="utf-8")
    (raw_dir / "atom_pocket.pdb").write_text("HETATM\nEND\n", encoding="utf-8")
    (raw_dir / "pocket_metadata.json").write_text(
        json.dumps(
            {
                "center": [0, 0, 0],
                "bbox": {"min": [0, 0, 0], "max": [1, 1, 1]},
                "residue_ids": ["A:1"],
                "atom_ids": [1],
            }
        ),
        encoding="utf-8",
    )

    result = _load_adapter().adapt_legacy_outputs(
        request={
            "task": {
                "id": "example-task",
                "tool_slug": "standard-pocket-adapter-template",
                "tool_version": "0.1.0",
            }
        },
        raw_output_dir=raw_dir,
        output_dir=output_dir,
    )

    assert result["result_version"] == "aidd.sciminer/result.v2"
    assert result["artifacts"]["pocket"]["type"] == "binding_pocket@1"
    assert set(result["artifacts"]["pocket"]["files"]) == {
        "residue_pocket_pdb",
        "atom_pocket_pdb",
        "pocket_metadata_json",
    }
    assert result["artifacts"]["pocket"]["metadata"]["source_protein_ref"] == "input:protein"
