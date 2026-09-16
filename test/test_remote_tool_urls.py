from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.remote_tools.urls import (
    RemoteToolUrlError,
    remote_endpoint_url,
    remote_result_url,
)


def test_remote_endpoint_url_expands_endpoint_templates() -> None:
    config = {
        "base_url": "https://model.example.com/",
        "endpoints": {"status": "/runs/{remote_run_id}"},
    }

    assert remote_endpoint_url(config, "status", remote_run_id="run-1") == (
        "https://model.example.com/runs/run-1"
    )


def test_remote_endpoint_url_rejects_missing_base_or_endpoint_path() -> None:
    with pytest.raises(RemoteToolUrlError, match="Missing base_url"):
        remote_endpoint_url({"endpoints": {"invoke": "/invoke"}}, "invoke")

    with pytest.raises(RemoteToolUrlError, match="Missing endpoint path"):
        remote_endpoint_url({"base_url": "https://model.example.com", "endpoints": {}}, "invoke")

    with pytest.raises(RemoteToolUrlError, match="Missing endpoint path"):
        remote_endpoint_url(
            {"base_url": "https://model.example.com", "endpoints": {"invoke": "invoke"}},
            "invoke",
        )


def test_remote_result_url_resolves_relative_file_urls_against_base_url() -> None:
    assert remote_result_url("https://model.example.com/", "/runs/run-1/file.pdb") == (
        "https://model.example.com/runs/run-1/file.pdb"
    )
    assert remote_result_url("https://model.example.com", "https://cdn.example.com/file.pdb") == (
        "https://cdn.example.com/file.pdb"
    )
