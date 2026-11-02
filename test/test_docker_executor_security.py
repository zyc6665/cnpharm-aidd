"""Docker 执行器沙箱安全回归测试。"""

from types import SimpleNamespace

import pytest

from app.tasks.executor import DockerExecutor, TaskExecutionError


def build_executor(*, image: str, command: list[str], params: dict | None = None) -> DockerExecutor:
    task = SimpleNamespace(
        id="task-1",
        user_id="user-1",
        inputs=SimpleNamespace(params=params) if params is not None else None,
    )
    tool_version = SimpleNamespace(
        config={
            "type": "docker_image",
            "image": image,
            "command": command,
        }
    )
    return DockerExecutor(task, tool_version)


def test_docker_command_enables_required_sandbox_restrictions() -> None:
    executor = build_executor(
        image="scitool/docking:v1.0.0",
        command=["python", "/app/dock.py"],
        params={"exhaustiveness": 8},
    )

    command = executor._build_docker_command(
        "scitool/docking:v1.0.0",
        ["python", "/app/dock.py"],
        "/tmp/task-1",
        gpu_required=False,
    )

    assert ["--security-opt", "no-new-privileges:true"] == command[
        command.index("--security-opt") : command.index("--security-opt") + 2
    ]
    assert ["--cap-drop", "ALL"] == command[
        command.index("--cap-drop") : command.index("--cap-drop") + 2
    ]
    assert ["--pids-limit", "256"] == command[
        command.index("--pids-limit") : command.index("--pids-limit") + 2
    ]


@pytest.mark.parametrize(
    "command",
    [
        ["python", "/app/run.py;curl attacker"],
        ["bash", "-c", "python /app/run.py"],
    ],
)
def test_docker_command_rejects_shell_control_arguments(command: list[str]) -> None:
    executor = build_executor(image="scitool/docking:v1.0.0", command=command)

    with pytest.raises(TaskExecutionError, match="不安全的 Shell 控制"):
        executor._build_docker_command(
            "scitool/docking:v1.0.0", command, "/tmp/task-1", gpu_required=False
        )


def test_docker_command_rejects_shell_control_in_task_params() -> None:
    executor = build_executor(
        image="scitool/docking:v1.0.0",
        command=["python", "/app/dock.py"],
        params={"ligand": "input.sdf;rm -rf /"},
    )

    with pytest.raises(TaskExecutionError, match="不安全的 Shell 控制"):
        executor._build_docker_command(
            "scitool/docking:v1.0.0", ["python", "/app/dock.py"], "/tmp/task-1", False
        )


def test_docker_command_requires_digest_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.tasks.executors.docker_security.settings.ENVIRONMENT", "production")
    executor = build_executor(image="scitool/docking:v1.0.0", command=["python", "/app/dock.py"])

    with pytest.raises(TaskExecutionError, match="不可变摘要"):
        executor._build_docker_command(
            "scitool/docking:v1.0.0", ["python", "/app/dock.py"], "/tmp/task-1", False
        )


def test_docker_command_uses_resource_limits_and_allocated_gpu_device() -> None:
    executor = build_executor(
        image="scitool/docking@sha256:" + "a" * 64,
        command=["python", "/app/dock.py"],
    )
    executor.config.update(
        {
            "cpu_limit": 16,
            "memory_limit": "64g",
            "gpu_config": {"count": 1, "device": "2"},
        }
    )

    command = executor._build_docker_command(
        "scitool/docking@sha256:" + "a" * 64,
        ["python", "/app/dock.py"],
        "/tmp/task-1",
        gpu_required=True,
    )

    assert ["--memory", "64g"] == command[command.index("--memory") : command.index("--memory") + 2]
    assert ["--cpus", "16"] == command[command.index("--cpus") : command.index("--cpus") + 2]
    assert ["--gpus", "device=2"] == command[command.index("--gpus") : command.index("--gpus") + 2]
