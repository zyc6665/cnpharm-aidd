"""AIDD task payload mapping tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.capabilities import get_capability  # noqa: E402
from app.agents.aidd.payloads import build_agent_task_payload  # noqa: E402


def test_ssh_job_payload_maps_file_fields_to_runtime_input_paths() -> None:
    capability = get_capability("gcdm-pocket-generation")
    payload = build_agent_task_payload(
        capability=capability,
        executor_type="ssh_job",
        semantic_files={
            "pocket_pdb": {
                "file_id": "file-pocket",
                "filename": "pocket_001.pdb",
                "download_url": "/api/v1/files/file-pocket/download",
            }
        },
        step_params={"params.n_samples": 16},
    )

    assert payload.params["input_files"]["pocket_pdb"] == "input/pocket_001.pdb"
    assert payload.params["params"]["n_samples"] == 16
    assert payload.file_ids == ["file-pocket"]


def test_ssh_job_payload_wraps_plain_file_fields_under_input_files() -> None:
    capability = get_capability("lvpocket-pocket-prediction")
    payload = build_agent_task_payload(
        capability=capability,
        executor_type="ssh_job",
        semantic_files={
            "protein_pdb": {
                "file_id": "file-protein",
                "filename": "protein.pdb",
                "download_url": "/api/v1/files/file-protein/download",
            }
        },
        step_params={},
    )

    assert payload.params["input_files"]["protein_pdb"] == "input/protein.pdb"
    assert "protein_pdb" not in payload.params
    assert payload.file_ids == ["file-protein"]


def test_remote_payload_maps_file_fields_to_download_urls() -> None:
    capability = get_capability("lvpocket-pocket-prediction")
    payload = build_agent_task_payload(
        capability=capability,
        executor_type="remote_api",
        semantic_files={
            "protein_pdb": {
                "file_id": "file-protein",
                "filename": "protein.pdb",
                "download_url": "/api/v1/files/file-protein/download",
            }
        },
        step_params={},
    )

    assert payload.params["protein_pdb"] == "/api/v1/files/file-protein/download"
    assert payload.file_ids == ["file-protein"]
