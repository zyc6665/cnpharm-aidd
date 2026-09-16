from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.remote_tools.results import (
    iter_remote_result_artifacts,
    remote_result_filename,
    remote_status_message,
    remote_status_progress,
)


def test_remote_status_message_prefers_message_then_error_details() -> None:
    assert remote_status_message({"message": " Running "}) == "Running"
    assert remote_status_message({"error": {"message": "model crashed"}}) == "model crashed"
    assert remote_status_message({"error": "failed"}) == "failed"
    assert remote_status_message({}) == "Remote tool run status updated"


def test_remote_status_progress_clamps_numeric_values_and_marks_success_complete() -> None:
    assert remote_status_progress({"progress": -10}, "running") == 0.0
    assert remote_status_progress({"progress": 150}, "running") == 100.0
    assert remote_status_progress({}, "success") == 100.0
    assert remote_status_progress({}, "running") is None


def test_remote_result_filename_uses_safe_basename_fallbacks() -> None:
    assert remote_result_filename({"filename": "nested/result.pdb"}, "pocket") == "result.pdb"
    assert remote_result_filename({"path": "outputs/report.json"}, "report") == "report.json"
    assert remote_result_filename({}, "scores") == "scores.dat"


def test_iter_remote_result_artifacts_handles_lists_dicts_and_nested_lists() -> None:
    assert list(iter_remote_result_artifacts([
        {"ref": "pocket", "files": {}},
        {"name": "report", "files": {}},
        "ignore",
    ])) == [
        ("pocket", {"ref": "pocket", "files": {}}),
        ("report", {"name": "report", "files": {}}),
    ]
    assert list(iter_remote_result_artifacts({
        "pockets": [{"files": {"pdb": {}}}],
        "metrics": {"files": {"json": {}}},
    })) == [
        ("pockets[0]", {"files": {"pdb": {}}}),
        ("metrics", {"files": {"json": {}}}),
    ]
