"""Task executor resolver tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tasks.executors.base import BaseExecutor  # noqa: E402
from app.tasks.executors.errors import TaskExecutionError  # noqa: E402
from app.tasks.executors.resolver import ExecutorResolver  # noqa: E402


class FakeExecutor(BaseExecutor):
    async def execute(self) -> dict[str, object]:
        return {"success": True}


def test_executor_resolver_resolves_registered_type_and_preserves_aliases():
    resolver = ExecutorResolver({"fake": FakeExecutor, "legacy-fake": FakeExecutor})

    assert resolver.resolve("fake") is FakeExecutor
    assert resolver.resolve("legacy-fake") is FakeExecutor
    assert resolver.supported_types() == ("fake", "legacy-fake")


def test_executor_resolver_raises_platform_error_for_unknown_type():
    resolver = ExecutorResolver({"fake": FakeExecutor})

    with pytest.raises(TaskExecutionError, match="不支持的执行器类型"):
        resolver.resolve("unknown")
