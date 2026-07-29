"""Python 脚本执行器信任边界回归测试。"""

import hashlib
from types import SimpleNamespace

import pytest

from app.tasks.executor import PythonScriptExecutor, TaskExecutionError


def build_executor(script_content: str) -> PythonScriptExecutor:
    task = SimpleNamespace(id="task-1", user_id="user-1", inputs=None)
    tool_version = SimpleNamespace(
        config={"type": "python_script", "script_content": script_content}
    )
    return PythonScriptExecutor(task, tool_version)


def test_python_script_rejects_untrusted_content_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.tasks.executor.settings.ENVIRONMENT", "production")
    monkeypatch.setattr("app.tasks.executor.settings.TRUSTED_PYTHON_SCRIPT_SHA256", [])
    executor = build_executor("print('untrusted')")

    with pytest.raises(TaskExecutionError, match="trusted SHA-256"):
        executor._validate_script_trust("print('untrusted')", None)


def test_python_script_accepts_allowlisted_content_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_content = "print('trusted')"
    monkeypatch.setattr("app.tasks.executor.settings.ENVIRONMENT", "production")
    monkeypatch.setattr(
        "app.tasks.executor.settings.TRUSTED_PYTHON_SCRIPT_SHA256",
        [hashlib.sha256(script_content.encode("utf-8")).hexdigest()],
    )
    executor = build_executor(script_content)

    executor._validate_script_trust(script_content, None)
