"""AIDD built-ins execute through the platform TaskExecutor."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / 'backend'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tasks.executor import TaskExecutor  # noqa: E402


def test_task_executor_resolves_builtin_executor() -> None:
    task = SimpleNamespace(id='task-1')
    tool_version = SimpleNamespace(config={'type': 'builtin', 'builtin_slug': 'builtin-sdf-to-pdb'})

    executor = TaskExecutor(task, tool_version)._get_executor()

    assert executor.__class__.__name__ == 'BuiltinExecutor'
