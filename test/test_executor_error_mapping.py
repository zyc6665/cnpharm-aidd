"""执行器把「已知原因」的失败报成人话，而不是「未知错误」。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.common.exceptions import ValidationException
from app.tasks.executors.errors import TaskExecutionError
from app.tasks.executors.factory import TaskExecutor


class _RaisingExecutor:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def execute(self):
        raise self._exc


def _build_executor(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> TaskExecutor:
    task = SimpleNamespace(
        id="task-1",
        status="running",
        extra_data={},
        progress=0.0,
        error_message=None,
    )
    tool_version = SimpleNamespace(config={"type": "builtin"}, id="tv-1")
    executor = TaskExecutor(task, tool_version)  # type: ignore[arg-type]

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(executor, "_acquire_resources", noop)
    monkeypatch.setattr(executor, "_allocate_gpu", noop)
    monkeypatch.setattr(executor, "_release_gpu", noop)
    monkeypatch.setattr(executor, "_release_resource_lease", noop)
    monkeypatch.setattr(executor, "_get_executor", lambda: _RaisingExecutor(exc))
    return executor


@pytest.mark.asyncio
async def test_validation_error_is_reported_with_its_reason(monkeypatch):
    # 真实场景：蛋白制备缺 obabel，内置工具抛 ValidationException，
    # 之前被包成「未知错误：…」，用户看不出是自己传错还是环境缺件。
    executor = _build_executor(
        monkeypatch,
        ValidationException("蛋白制备需要 obabel 将 prepared PDB 转为 receptor PDBQT"),
    )

    with pytest.raises(TaskExecutionError) as excinfo:
        await executor.execute()

    assert "任务无法执行" in excinfo.value.message
    assert "obabel" in excinfo.value.message
    assert "未知错误" not in excinfo.value.message


@pytest.mark.asyncio
async def test_unexpected_error_stays_labelled_as_unknown(monkeypatch):
    executor = _build_executor(monkeypatch, RuntimeError("boom"))

    with pytest.raises(TaskExecutionError) as excinfo:
        await executor.execute()

    assert "未知错误" in excinfo.value.message
