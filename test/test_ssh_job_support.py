"""ssh_job 执行方式的后端支持测试。"""

from __future__ import annotations

import os
import json
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


def _v2_manifest() -> dict:
    return {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": "standard-ssh-tool",
            "name": "Standard SSH Tool",
            "version": "1.0.0",
        },
        "artifacts": {
            "inputs": [{"name": "protein", "type": "protein_structure@1", "required": True}],
            "outputs": [{"name": "report", "type": "run_report@1"}],
        },
        "parameters_schema": {"type": "object"},
        "runtime": {
            "python": "3.10",
            "executor_support": ["ssh_docker_exec"],
            "selection_policy": "test runtime",
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": "registry.example/sciminer/standard-ssh-tool:1.0.0",
                    "image_digest": "sha256:test",
                },
                "fallback": {
                    "kind": "conda_pack",
                    "uri": "artifacts://model-envs/standard-ssh-tool/1.0.0/conda-env.tar.gz",
                    "sha256": "test",
                },
            },
            "weights": {
                "manifest_uri": "artifacts://model-weights/standard-ssh-tool/1.0.0/weights.json",
                "manifest_sha256": "test",
            },
            "cache_policy": {
                "key_fields": ["metadata.slug", "metadata.version"],
                "mutable_host_paths_forbidden": True,
            },
        },
        "variants": [
            {
                "name": "cpu",
                "accelerator": "cpu",
                "executor_types": ["remote_job"],
                "entrypoint": ["runner/entrypoint.sh"],
            }
        ],
    }


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


@pytest.mark.asyncio
async def test_ssh_job_executor_writes_standard_request_from_input_bindings(
    monkeypatch,
    tmp_path,
) -> None:
    """v2 Tool Package + input_bindings 时，SSH params.json 应是标准 request.v1。"""
    task = _build_task("task-standard")
    task.extra_data = {"input_bindings": {"protein": "artifact-version-1"}}
    task.inputs = SimpleNamespace(params={"threshold": 0.5}, file_ids=["legacy-file-id"])
    config = {
        "type": "ssh_job",
        "host": "gpu-node-01.internal",
        "username": "runner",
        "runner_mode": "shell",
        "remote_base_dir": "/srv/platform-jobs",
        "entrypoint": "/opt/models/platform_run.sh",
        "tool_package_manifest": _v2_manifest(),
        "variant": "cpu",
        "accelerator": "cpu",
    }
    executor = SSHJobExecutor(task, _build_tool_version(config))
    called: dict[str, object] = {}

    async def fake_get_async_session():
        yield object()

    class FakeStandardRequest:
        def model_dump(self, mode: str = "json") -> dict:
            return {
                "request_version": "aidd.sciminer/request.v1",
                "task": {
                    "id": "task-standard",
                    "tool_slug": "standard-ssh-tool",
                    "tool_version": "1.0.0",
                },
                "inputs": {"protein": {"artifact_version_id": "artifact-version-1"}},
                "parameters": {"threshold": 0.5},
                "execution": {"variant": "cpu", "accelerator": "cpu"},
            }

    async def fake_build_standard_execution_request(
        db,
        *,
        task,
        tool_package_manifest,
        input_bindings,
        parameters,
        work_dir,
        execution_context,
    ):
        called["db"] = db
        called["input_bindings"] = dict(input_bindings)
        called["parameters"] = dict(parameters)
        called["work_dir"] = Path(work_dir)
        called["variant"] = execution_context.variant
        called["accelerator"] = execution_context.accelerator
        called["slug"] = tool_package_manifest.metadata.slug
        return FakeStandardRequest()

    async def fail_legacy_file_staging(_input_dir: str):
        raise AssertionError("legacy file_id staging should not run for standard input_bindings")

    monkeypatch.setenv("TASK_WORK_DIR", str(tmp_path))
    monkeypatch.setattr("app.tasks.executors.ssh_job.get_async_session", fake_get_async_session)
    monkeypatch.setattr(
        "app.tasks.executors.ssh_job.build_standard_execution_request",
        fake_build_standard_execution_request,
    )
    monkeypatch.setattr(executor, "_prepare_input_files", fail_legacy_file_staging)

    bundle = await executor._prepare_local_task_bundle()
    payload = json.loads(Path(bundle["params_path"]).read_text(encoding="utf-8"))

    assert payload["request_version"] == "aidd.sciminer/request.v1"
    assert payload["inputs"]["protein"]["artifact_version_id"] == "artifact-version-1"
    assert payload["parameters"] == {"threshold": 0.5}
    assert called["input_bindings"] == {"protein": "artifact-version-1"}
    assert called["parameters"] == {"threshold": 0.5}
    assert called["variant"] == "cpu"
    assert called["accelerator"] == "cpu"


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


def test_ssh_job_executor_keeps_standard_result_v2_schema_clean() -> None:
    """平台内部 output_file_ids 不应写进标准 result.v2 本体。"""
    standard_result = {
        "result_version": "aidd.sciminer/result.v2",
        "artifacts": {},
        "relations": [],
    }
    legacy_result = {"success": True}

    assert (
        SSHJobExecutor._attach_output_file_ids(standard_result, ["file-1"])
        is standard_result
    )
    assert "output_file_ids" not in standard_result
    assert SSHJobExecutor._attach_output_file_ids(legacy_result, ["file-1"]) == {
        "success": True,
        "output_file_ids": ["file-1"],
    }


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
