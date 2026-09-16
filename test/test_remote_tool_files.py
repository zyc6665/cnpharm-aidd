from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.files.remote_access_tokens import validate_remote_file_access_token


def _remote_tool_files_module():
    try:
        from app.remote_tools import files
    except (ImportError, ModuleNotFoundError):
        pytest.fail("app.remote_tools.files module is missing")
    return files


def test_remote_file_download_url_signs_file_for_task_and_uses_platform_base_url() -> None:
    files = _remote_tool_files_module()

    url = files.remote_file_download_url(
        file_id="file-1",
        task_id="task-1",
        config={"platform_base_url": "https://platform.example.com/", "input_url_expires_in_sec": 300},
    )
    parsed = urlparse(url)
    token = parse_qs(parsed.query)["token"][0]

    assert url.startswith("https://platform.example.com/api/v1/files/file-1/download")
    assert validate_remote_file_access_token(token, file_id="file-1", task_id="task-1")["task_id"] == "task-1"


def test_remote_file_payload_normalizes_file_metadata() -> None:
    files = _remote_tool_files_module()
    file_record = SimpleNamespace(
        filename="protein.pdb",
        sha256="A" * 64,
        content_type="chemical/x-pdb",
    )

    assert files.remote_file_payload(
        file_record,
        download_url="https://platform.example.com/api/v1/files/file-1/download?token=abc",
    ) == {
        "url": "https://platform.example.com/api/v1/files/file-1/download?token=abc",
        "filename": "protein.pdb",
        "sha256": "a" * 64,
        "content_type": "chemical/x-pdb",
    }
