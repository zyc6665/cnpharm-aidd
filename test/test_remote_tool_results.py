from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


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


def test_remote_status_state_normalizes_success_message_and_progress() -> None:
    from app.remote_tools import results

    build_state = getattr(results, "remote_status_state", None)

    assert callable(build_state)
    state = build_state({"status": "SUCCESS", "message": " Done ", "progress": 45})

    assert state.value == "success"
    assert state.message == "Done"
    assert state.progress == 45.0
    assert state.is_success is True
    assert state.can_poll is False
    assert state.error_message is None


def test_remote_status_state_maps_pollable_and_terminal_errors() -> None:
    from app.remote_tools import results

    build_state = getattr(results, "remote_status_state", None)

    assert callable(build_state)
    assert build_state({"status": "running"}).can_poll is True
    assert build_state({"status": "failure", "error": "model failed"}).error_message == "model failed"
    assert build_state({"status": "canceled"}).error_message == "Remote tool run was canceled"
    assert build_state({"status": "paused"}).error_message == "Unsupported remote run status: paused"


def test_iter_remote_log_messages_strips_non_empty_messages() -> None:
    from app.remote_tools import results

    iter_messages = getattr(results, "iter_remote_log_messages", None)

    assert callable(iter_messages)
    assert list(iter_messages({"items": [{"message": " queued "}, {"message": ""}, {}, "ignore"]})) == [
        "queued"
    ]
    assert list(iter_messages({"items": "not-a-list"})) == []


def test_remote_log_next_cursor_keeps_existing_cursor_without_next_cursor() -> None:
    from app.remote_tools import results

    next_cursor = getattr(results, "remote_log_next_cursor", None)

    assert callable(next_cursor)
    assert next_cursor({"next_cursor": "cursor-2"}, "cursor-1") == "cursor-2"
    assert next_cursor({"next_cursor": ""}, "cursor-1") == "cursor-1"
    assert next_cursor({}, None) is None


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


def test_verify_remote_result_file_checksum_returns_actual_sha_without_declared_sha() -> None:
    from app.remote_tools import results

    content = b"remote result file"
    verify_checksum = getattr(results, "verify_remote_result_file_checksum", None)

    assert callable(verify_checksum)
    assert verify_checksum({"path": "outputs/result.pdb"}, "pdb", content) == hashlib.sha256(content).hexdigest()


def test_verify_remote_result_file_checksum_accepts_declared_sha_case_insensitively() -> None:
    from app.remote_tools import results

    content = b"remote result file"
    digest = hashlib.sha256(content).hexdigest()

    assert results.verify_remote_result_file_checksum(
        {"path": "outputs/result.pdb", "sha256": digest.upper()},
        "pdb",
        content,
    ) == digest


def test_verify_remote_result_file_checksum_rejects_declared_sha_mismatch() -> None:
    from app.remote_tools import results

    content = b"remote result file"
    digest = hashlib.sha256(content).hexdigest()

    with pytest.raises(
        ValueError,
        match=f"Remote result file checksum mismatch for outputs/result.pdb: declared deadbeef, actual {digest}",
    ):
        results.verify_remote_result_file_checksum(
            {"path": "outputs/result.pdb", "sha256": "deadbeef"},
            "pdb",
            content,
        )


def test_remote_result_file_record_data_builds_output_record_fields() -> None:
    from app.remote_tools import results

    build_record_data = getattr(results, "remote_result_file_record_data", None)

    assert callable(build_record_data)
    assert build_record_data(
        file_ref={"path": "outputs/result.pdb", "content_type": "chemical/x-pdb"},
        artifact_ref="pocket[0]",
        artifact={"ref": "pocket"},
        role="pdb",
        content_length=6,
        sha256="a" * 64,
        owner_id="user-1",
    ) == {
        "filename": "result.pdb",
        "content_type": "chemical/x-pdb",
        "size_bytes": 6,
        "sha256": "a" * 64,
        "storage_path": "pending",
        "source_type": "tool_output",
        "owner_id": "user-1",
        "is_public": False,
        "is_permanent": False,
        "file_meta": {
            "remote_result_path": "outputs/result.pdb",
            "relative_path": "outputs/result.pdb",
            "artifact_ref": "pocket",
            "standard_artifact_output": "pocket[0]",
            "file_role": "pdb",
        },
    }
