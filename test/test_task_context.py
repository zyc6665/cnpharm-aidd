"""Task context compatibility helper tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.task_context import (  # noqa: E402
    set_task_project_id,
    task_extra_data,
    task_project_id,
)


def test_task_context_reads_and_writes_project_id_without_mutating_metadata():
    original = {"project_id": "project-1", "source": "workflow"}
    task = SimpleNamespace(extra_data=original)

    assert task_project_id(task) == "project-1"
    assert task_extra_data(task) == original

    updated = set_task_project_id(original, "project-2")
    assert updated == {"project_id": "project-2", "source": "workflow"}
    assert original == {"project_id": "project-1", "source": "workflow"}


def test_task_context_ignores_missing_or_empty_project_id():
    assert task_project_id(SimpleNamespace(extra_data={})) is None
    assert task_project_id(SimpleNamespace(extra_data=None)) is None
    assert set_task_project_id({"project_id": "project-1"}, None) == {}
