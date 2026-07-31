"""Self-tests that package authors should keep with every Tool Package."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import ValidationError


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _load_result_parser():
    path = PACKAGE_ROOT / "runner" / "result_parser.py"
    spec = importlib.util.spec_from_file_location("tool_result_parser", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_result_parser_accepts_artifacts_with_matching_checksums(tmp_path: Path):
    payloads = {
        "pockets": ("pocket_result", "pockets.json", "{\"pockets\": []}"),
        "report": ("run_report", "report.json", "{\"status\": \"succeeded\"}"),
    }
    result = {}
    import hashlib

    for name, (artifact_type, filename, content) in payloads.items():
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        result[name] = {
            "artifact_type": artifact_type,
            "path": filename,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")

    parsed = _load_result_parser().parse_result(result_path, tmp_path)

    assert set(parsed) == {"pockets", "report"}


def test_result_parser_rejects_artifact_outside_output_directory(tmp_path: Path):
    result = {
        "pockets": {
            "artifact_type": "pocket_result",
            "path": "../outside.json",
            "sha256": "0" * 64,
        },
        "report": {
            "artifact_type": "run_report",
            "path": "report.json",
            "sha256": "0" * 64,
        },
    }
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(ValueError, match="escapes output directory"):
        _load_result_parser().parse_result(result_path, tmp_path)


def test_output_schema_rejects_swapped_artifact_types(tmp_path: Path):
    import hashlib

    for filename in ("pockets.json", "report.json"):
        (tmp_path / filename).write_text("{}", encoding="utf-8")
    digest = hashlib.sha256(b"{}").hexdigest()
    result = {
        "pockets": {
            "artifact_type": "run_report",
            "path": "pockets.json",
            "sha256": digest,
        },
        "report": {
            "artifact_type": "pocket_result",
            "path": "report.json",
            "sha256": digest,
        },
    }
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(ValidationError):
        _load_result_parser().parse_result(result_path, tmp_path)
