"""Python 脚本执行器信任边界回归测试。"""

import hashlib
from types import SimpleNamespace

import pytest

from app.tasks.executor import PythonScriptExecutor, TaskExecutionError


def build_executor(
    script_content: str | None = None,
    *,
    config: dict | None = None,
) -> PythonScriptExecutor:
    task = SimpleNamespace(
        id="task-1",
        user_id="user-1",
        inputs=SimpleNamespace(params={"sample_count": 4}),
    )
    tool_version = SimpleNamespace(
        config=config or {"type": "python_script", "script_content": script_content}
    )
    return PythonScriptExecutor(task, tool_version)


def test_python_script_rejects_untrusted_content_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.tasks.executors.script_trust.settings.ENVIRONMENT", "production")
    monkeypatch.setattr("app.tasks.executors.script_trust.settings.TRUSTED_PYTHON_SCRIPT_SHA256", [])
    executor = build_executor("print('untrusted')")

    with pytest.raises(TaskExecutionError, match="可信 SHA-256"):
        executor._validate_script_trust("print('untrusted')", None)


def test_python_script_accepts_allowlisted_content_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_content = "print('trusted')"
    monkeypatch.setattr("app.tasks.executors.script_trust.settings.ENVIRONMENT", "production")
    monkeypatch.setattr(
        "app.tasks.executors.script_trust.settings.TRUSTED_PYTHON_SCRIPT_SHA256",
        [hashlib.sha256(script_content.encode("utf-8")).hexdigest()],
    )
    executor = build_executor(script_content)

    executor._validate_script_trust(script_content, None)


@pytest.mark.asyncio
async def test_python_script_passes_configured_arguments_without_splitting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    captured_command: list[str] = []

    def fake_run(command, **kwargs):
        captured_command.extend(command)
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setenv("TASK_WORK_DIR", str(tmp_path))
    monkeypatch.setattr("app.tasks.executors.script_trust.settings.ENVIRONMENT", "development")
    monkeypatch.setattr("app.tasks.executors.script_trust.settings.TRUSTED_PYTHON_SCRIPT_SHA256", [])
    monkeypatch.setattr("app.tasks.executors.python_script.subprocess.run", fake_run)
    executor = build_executor(
        config={
            "type": "python_script",
            "script_path": "/opt/platform/run_model.py",
            "args": ["--model-name", "lead model v2", "--device", "cpu"],
        }
    )

    await executor.execute()

    assert captured_command[:6] == [
        "python",
        "/opt/platform/run_model.py",
        "--model-name",
        "lead model v2",
        "--device",
        "cpu",
    ]
    assert captured_command[6] == "--params-file"
    assert captured_command[8] == "--output-dir"


@pytest.mark.asyncio
async def test_python_script_strips_sensitive_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    captured_env: dict[str, str] = {}

    def fake_run(command, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setenv("TASK_WORK_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pw@db/app")
    monkeypatch.setenv("JWT_SECRET_KEY", "super-secret-jwt-key")
    monkeypatch.setenv("MINIO_SECRET_KEY", "minio-secret")
    monkeypatch.setenv("PLATFORM_HARMLESS_FLAG", "ok")
    monkeypatch.setattr("app.tasks.executors.script_trust.settings.ENVIRONMENT", "development")
    monkeypatch.setattr("app.tasks.executors.script_trust.settings.TRUSTED_PYTHON_SCRIPT_SHA256", [])
    monkeypatch.setattr("app.tasks.executors.python_script.subprocess.run", fake_run)
    executor = build_executor(config={"type": "python_script", "script_path": "/opt/platform/run_model.py"})

    await executor.execute()

    assert "DATABASE_URL" not in captured_env
    assert "JWT_SECRET_KEY" not in captured_env
    assert "MINIO_SECRET_KEY" not in captured_env
    assert captured_env.get("PLATFORM_HARMLESS_FLAG") == "ok"
    assert captured_env.get("PYTHONPATH", "").startswith(str(tmp_path))


@pytest.mark.asyncio
async def test_python_script_rejects_non_string_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.tasks.executors.script_trust.settings.ENVIRONMENT", "development")
    monkeypatch.setattr("app.tasks.executors.script_trust.settings.TRUSTED_PYTHON_SCRIPT_SHA256", [])
    executor = build_executor(
        config={
            "type": "python_script",
            "script_path": "/opt/platform/run_model.py",
            "args": ["--batch-size", 32],
        }
    )

    with pytest.raises(TaskExecutionError, match="必须是字符串数组"):
        await executor.execute()
