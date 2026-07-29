"""ssh_job 执行方式的后端支持测试。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tasks.executor import SSHJobExecutor, TaskExecutor
from app.tasks.queue_manager import TaskQueue, TaskQueueManager
from app.config import bootstrap_process_env


def _build_task(task_id: str = "task-123") -> SimpleNamespace:
    return SimpleNamespace(
        id=task_id,
        user_id="user-123",
        inputs=SimpleNamespace(params={"num_samples": 4}, file_ids=[]),
    )


def _build_tool_version(config: dict) -> SimpleNamespace:
    return SimpleNamespace(config=config)


def test_determine_queue_routes_non_gpu_ssh_job_to_cpu_queue() -> None:
    """ssh_job 默认应进入 CPU 队列，而不是 API 默认队列。"""
    queue = TaskQueueManager.determine_queue(
        {
            "type": "ssh_job",
            "gpu_required": False,
        }
    )

    assert queue == TaskQueue.CPU_QUEUE.value


def test_determine_queue_uses_explicit_tool_gpu_requirement() -> None:
    """队列路由应以 Tool.gpu_required 为准，而非版本 JSON 配置。"""
    queue = TaskQueueManager.determine_queue(
        {"type": "docker_image", "gpu_required": False},
        gpu_required=True,
    )

    assert queue == TaskQueue.GPU_QUEUE.value


def test_task_executor_returns_ssh_job_executor() -> None:
    """执行器工厂应识别 ssh_job。"""
    executor = TaskExecutor(
        _build_task(),
        _build_tool_version(
            {
                "type": "ssh_job",
                "host": "gpu-node-01.internal",
                "username": "runner",
                "auth_ref": "ssh_gpu_node_01",
                "runner_mode": "shell",
                "remote_base_dir": "/srv/platform-jobs",
                "entrypoint": "/opt/models/platform_run.sh",
            }
        ),
    )._get_executor()

    assert isinstance(executor, SSHJobExecutor)


def test_ssh_job_executor_builds_container_runtime_paths_and_command() -> None:
    """docker_exec 模式应区分宿主机目录和容器内目录。"""
    config = {
        "type": "ssh_job",
        "host": "gpu-node-01.internal",
        "username": "runner",
        "auth_ref": "ssh_gpu_node_01",
        "runner_mode": "docker_exec",
        "remote_base_dir": "/srv/platform-jobs",
        "container_base_dir": "/workspace/platform-jobs",
        "entrypoint": "/app/platform_run.sh",
        "container_name": "targetdiff-prod",
        "env": {"CUDA_VISIBLE_DEVICES": "0"},
    }
    executor = SSHJobExecutor(_build_task("task-123"), _build_tool_version(config))

    remote_paths = executor._build_remote_paths()
    command = executor._build_remote_exec_command(remote_paths)

    assert remote_paths["host_task_dir"] == "/srv/platform-jobs/task-123"
    assert remote_paths["runtime_task_dir"] == "/workspace/platform-jobs/task-123"
    assert "docker exec targetdiff-prod bash -lc" in command
    assert "--output-dir /workspace/platform-jobs/task-123/output" in command
    assert "export CUDA_VISIBLE_DEVICES=0" in command


def test_ssh_job_executor_supports_password_auth(monkeypatch, tmp_path) -> None:
    """密码认证模式应正确解析 password_ref。"""
    password_file = tmp_path / "ssh_4090_password"
    password_file.write_text("super-secret\n", encoding="utf-8")
    monkeypatch.setenv("SSH_PASSWORD_REF_DIR", str(tmp_path))

    config = {
        "type": "ssh_job",
        "host": "4090",
        "username": "zhouyc",
        "auth_type": "password",
        "password_ref": "ssh_4090_password",
        "runner_mode": "shell",
        "remote_base_dir": "/srv/platform-jobs",
        "entrypoint": "/app/platform_run.sh",
        "strict_host_key_checking": False,
    }
    executor = SSHJobExecutor(_build_task("task-456"), _build_tool_version(config))

    auth_settings = executor._resolve_auth_settings()

    assert auth_settings["auth_type"] == "password"
    assert auth_settings["password"] == "super-secret"
    assert auth_settings["key_path"] is None


def test_ssh_job_executor_does_not_keep_sshpass_environment_helper() -> None:
    """SSH 密码只应交给 Paramiko，不应进入子进程环境变量。"""
    assert not hasattr(SSHJobExecutor, "_build_command_env")


@pytest.mark.asyncio
async def test_ssh_job_recovery_downloads_with_paramiko(monkeypatch, tmp_path) -> None:
    """远端结果补抓应复用 Paramiko，而非启动本地 ssh/scp 子进程。"""
    calls: list[str] = []

    class FakeTransport:
        def __init__(self, **kwargs) -> None:
            calls.append("init")

        def connect(self) -> None:
            calls.append("connect")

        def path_exists(self, remote_path: str) -> bool:
            calls.append(f"exists:{remote_path}")
            return True

        def download_tree(self, remote_dir: str, local_dir: str) -> None:
            calls.append(f"download:{remote_dir}")
            output_dir = Path(local_dir)
            output_dir.mkdir(parents=True)
            (output_dir / "result.json").write_text('{"success": true}', encoding="utf-8")

        def close(self) -> None:
            calls.append("close")

    config = {
        "type": "ssh_job",
        "host": "gpu-node-01.internal",
        "username": "runner",
        "runner_mode": "shell",
        "remote_base_dir": "/srv/platform-jobs",
        "entrypoint": "/opt/models/platform_run.sh",
    }
    executor = SSHJobExecutor(_build_task("task-recovery"), _build_tool_version(config))

    async def fake_collect_output_files(download_root: str) -> list[str]:
        return []

    monkeypatch.setenv("TASK_WORK_DIR", str(tmp_path))
    monkeypatch.setattr("app.tasks.executors.ssh_job.ParamikoSSHTransport", FakeTransport)
    monkeypatch.setattr(
        executor,
        "_resolve_auth_settings",
        lambda: {"auth_type": "password", "password": "secret", "key_path": None, "known_hosts_path": None},
    )
    monkeypatch.setattr(executor, "_collect_output_files", fake_collect_output_files)

    result = await executor.recover_remote_result()

    assert result is not None
    assert result["result"] == {"success": True}
    assert calls[0:2] == ["init", "connect"]
    assert any(call.startswith("exists:") for call in calls)
    assert any(call.startswith("download:") for call in calls)
    assert calls[-1] == "close"


def test_bootstrap_process_env_loads_secret_refs_from_dotenv(monkeypatch, tmp_path) -> None:
    """本地 .env 中的 SSH_PASSWORD_REF_* 应注入进程环境，供 ssh_job 执行器读取。"""
    env_file = tmp_path / ".env"
    env_file.write_text("SSH_PASSWORD_REF_SSH_4090_ZHOUYC=super-secret\n", encoding="utf-8")
    monkeypatch.delenv("SSH_PASSWORD_REF_SSH_4090_ZHOUYC", raising=False)

    bootstrap_process_env(str(env_file))

    assert os.environ.get("SSH_PASSWORD_REF_SSH_4090_ZHOUYC") == "super-secret"


def test_ssh_job_executor_zips_bulk_sdf_directory_outputs(tmp_path) -> None:
    """大量单分子 SDF 应打包成 ZIP，避免任务输出列表过长。"""
    output_root = tmp_path / "download" / "output"
    sdf_dir = output_root / "artifacts" / "SDF"
    sdf_dir.mkdir(parents=True)
    for index in range(12):
        (sdf_dir / f"{index}.sdf").write_text(f"mol-{index}\n", encoding="utf-8")
    (output_root / "artifacts" / "metadata.csv").write_text("index,sdf_file\n", encoding="utf-8")

    executor = SSHJobExecutor(
        _build_task("task-bulk-sdf"),
        _build_tool_version(
            {
                "type": "ssh_job",
                "host": "gpu-node-01.internal",
                "username": "runner",
                "runner_mode": "shell",
                "remote_base_dir": "/srv/platform-jobs",
                "entrypoint": "/opt/models/platform_run.sh",
                "output_globs": ["output/artifacts/**/*"],
            }
        ),
    )

    matched_files = executor._prepare_output_files_for_collection(
        str(tmp_path / "download"),
        str(output_root),
    )
    relative_paths = {
        Path(file_path).relative_to(output_root).as_posix()
        for file_path in matched_files
    }

    assert "artifacts/SDF.zip" in relative_paths
    assert "artifacts/metadata.csv" in relative_paths
    assert not any(path.startswith("artifacts/SDF/") for path in relative_paths)
