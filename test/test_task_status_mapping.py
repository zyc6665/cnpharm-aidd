"""Task and execution status mapping tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.task_status import (  # noqa: E402
    execution_state_to_task_status,
    task_status_to_api,
    task_status_to_execution_state,
)


def test_task_status_mapping_preserves_existing_api_values():
    assert task_status_to_api("PENDING") == "pending"
    assert task_status_to_api("SUCCESS") == "success"
    assert task_status_to_api("CANCELED") == "canceled"


def test_task_status_mapping_exposes_execution_contract_values():
    assert task_status_to_execution_state("PENDING") == "queued"
    assert task_status_to_execution_state("SUCCESS") == "succeeded"
    assert task_status_to_execution_state("FAILURE") == "failed"
    assert task_status_to_execution_state("CANCELED") == "cancelled"


def test_execution_status_mapping_accepts_both_cancel_spellings():
    assert execution_state_to_task_status("queued") == "PENDING"
    assert execution_state_to_task_status("succeeded") == "SUCCESS"
    assert execution_state_to_task_status("cancelled") == "CANCELED"
    assert execution_state_to_task_status("canceled") == "CANCELED"
