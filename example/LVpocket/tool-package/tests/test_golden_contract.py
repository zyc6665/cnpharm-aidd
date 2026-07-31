"""Package-local checks for the LVpocket golden input and result parser."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _load_result_parser():
    parser_path = PACKAGE_ROOT / "runner" / "result_parser.py"
    spec = importlib.util.spec_from_file_location("lvpocket_result_parser", parser_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_golden_input_checksum_matches_metadata():
    metadata = json.loads(
        (PACKAGE_ROOT / "golden" / "1a26.metadata.json").read_text(encoding="utf-8")
    )
    input_path = (PACKAGE_ROOT / "golden" / metadata["input"]["path"]).resolve()

    assert input_path.is_file()
    assert hashlib.sha256(input_path.read_bytes()).hexdigest() == metadata["input"]["sha256"]


def test_parser_accepts_matching_output_artifacts(tmp_path: Path):
    payloads = {
        "pockets": ("pocket_result", "pockets.json"),
        "report": ("run_report", "report.json"),
    }
    result = {}
    for name, (artifact_type, filename) in payloads.items():
        path = tmp_path / filename
        path.write_text("{}", encoding="utf-8")
        result[name] = {
            "artifact_type": artifact_type,
            "path": filename,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")

    parsed = _load_result_parser().parse_result(result_path, tmp_path)

    assert set(parsed) == {"pockets", "report"}


def test_parser_rejects_missing_result_json(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="result.json"):
        _load_result_parser().parse_result(tmp_path / "result.json", tmp_path)
