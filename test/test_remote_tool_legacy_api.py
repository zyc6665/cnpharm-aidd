from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.remote_tools.legacy_api import (
    build_legacy_remote_api_request_data,
    flatten_legacy_remote_api_params,
)


def test_build_legacy_remote_api_request_data_preserves_nested_params_shape() -> None:
    assert build_legacy_remote_api_request_data(
        task_id="task-1",
        input_params={
            "params": {"threshold": 0.5},
            "input_files": {"protein_pdb": "input/protein.pdb"},
        },
    ) == {
        "task_id": "task-1",
        "params": {"threshold": 0.5},
        "input_files": {"protein_pdb": "input/protein.pdb"},
    }


def test_build_legacy_remote_api_request_data_wraps_plain_params_and_files() -> None:
    assert build_legacy_remote_api_request_data(
        task_id="task-1",
        input_params={"threshold": 0.5},
        input_file_paths=["/work/input/protein.pdb"],
    ) == {
        "task_id": "task-1",
        "params": {"threshold": 0.5},
        "files": ["/work/input/protein.pdb"],
    }


def test_flatten_legacy_remote_api_params_json_encodes_nested_values() -> None:
    assert flatten_legacy_remote_api_params({
        "task_id": "task-1",
        "params": {"threshold": 0.5},
        "files": ["input/protein.pdb"],
        "dry_run": True,
    }) == {
        "task_id": "task-1",
        "params": '{"threshold": 0.5}',
        "files": '["input/protein.pdb"]',
        "dry_run": "True",
    }


def test_legacy_output_filename_prefers_name_then_filename_then_fallback() -> None:
    from app.remote_tools import legacy_api

    output_filename = getattr(legacy_api, "legacy_output_filename", None)

    assert callable(output_filename)
    assert output_filename({"name": "result.pdb", "filename": "ignored.dat"}, "fallback.dat") == "result.pdb"
    assert output_filename({"filename": "nested/report.json"}, "fallback.dat") == "nested/report.json"
    assert output_filename({}, "fallback.dat") == "fallback.dat"


def test_legacy_output_file_record_data_builds_tool_output_fields() -> None:
    from app.remote_tools import legacy_api

    build_record_data = getattr(legacy_api, "legacy_output_file_record_data", None)

    assert callable(build_record_data)
    assert build_record_data(
        filename="result.pdb",
        content_type="chemical/x-pdb",
        content=b"POCKET",
        owner_id="user-1",
    ) == {
        "filename": "result.pdb",
        "content_type": "chemical/x-pdb",
        "size_bytes": 6,
        "sha256": "fdda3539d63f1ec143ad7b54774b89be75ddfa1f4c3b5e33a41e8900e4589314",
        "source_type": "tool_output",
        "owner_id": "user-1",
        "is_public": False,
        "is_permanent": False,
    }
