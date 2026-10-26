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
    # 向后兼容：五态时代的 API 词表一个都不能变。
    assert task_status_to_api("PENDING") == "pending"
    assert task_status_to_api("RUNNING") == "running"
    assert task_status_to_api("SUCCESS") == "success"
    assert task_status_to_api("FAILURE") == "failure"
    assert task_status_to_api("CANCELED") == "canceled"


def test_task_status_mapping_exposes_queued_and_timeout_api_values():
    # docs/01 §10.2 与 docs/03 §3.4 的八态：新增「排队中」「已超时」。
    assert task_status_to_api("QUEUED") == "queued"
    assert task_status_to_api("TIMEOUT") == "timeout"


def test_task_status_mapping_exposes_execution_contract_values():
    # PENDING 与 QUEUED 不能撞同一个执行态：PENDING=created、QUEUED=queued。
    assert task_status_to_execution_state("PENDING") == "created"
    assert task_status_to_execution_state("QUEUED") == "queued"
    assert task_status_to_execution_state("SUCCESS") == "succeeded"
    assert task_status_to_execution_state("FAILURE") == "failed"
    assert task_status_to_execution_state("CANCELED") == "cancelled"
    assert task_status_to_execution_state("TIMEOUT") == "timeout"


def test_execution_status_mapping_accepts_both_cancel_spellings():
    assert execution_state_to_task_status("created") == "PENDING"
    assert execution_state_to_task_status("queued") == "QUEUED"
    assert execution_state_to_task_status("running") == "RUNNING"
    assert execution_state_to_task_status("succeeded") == "SUCCESS"
    assert execution_state_to_task_status("failed") == "FAILURE"
    assert execution_state_to_task_status("cancelled") == "CANCELED"
    assert execution_state_to_task_status("canceled") == "CANCELED"


def test_execution_status_mapping_maps_timeout_back_to_timeout_task_status():
    # 执行器中性词表里的 timeout 必须回到 TIMEOUT，而不是 FAILURE。
    assert execution_state_to_task_status("timeout") == "TIMEOUT"
    assert execution_state_to_task_status("timed_out") == "TIMEOUT"
