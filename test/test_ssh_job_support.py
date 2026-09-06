"""ssh_job 执行方式的后端支持测试。"""

from __future__ import annotations

import os
import json
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tasks.executor import SSHJobExecutor, TaskExecutor
from app.tasks.executors.ssh_payload import build_params_payload
from app.tasks.ssh_transport import ParamikoSSHTransport
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


def _v2_affinity_manifest() -> dict:
    manifest = _v2_manifest()
    manifest["metadata"] = {
        "slug": "msign-affinity-prediction",
        "name": "MSIGN Affinity",
        "version": "1.0.0",
    }
    manifest["artifacts"] = {
        "inputs": [
            {"name": "protein", "type": "protein_structure@1", "required": True},
            {"name": "ligand", "type": "ligand_structure@1", "required": True},
        ],
        "outputs": [{"name": "affinity", "type": "molecule_table@1"}],
    }
    return manifest


def _v2_admet_manifest() -> dict:
    manifest = _v2_manifest()
    manifest["metadata"] = {
        "slug": "molp-pc-property-prediction",
        "name": "MolP-PC Property Prediction",
        "version": "1.0.0",
    }
    manifest["artifacts"] = {
        "inputs": [{"name": "molecules", "type": "molecule_table@1", "required": True}],
        "outputs": [{"name": "properties", "type": "molecule_table@1"}],
    }
    return manifest


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


def test_determine_queue_routes_heavy_cpu_tools_to_heavy_compute_queue() -> None:
    queue = TaskQueueManager.determine_queue(
        {
            "type": "ssh_job",
            "gpu_required": False,
            "resource_profile": {
                "tier": "heavy",
                "cpu": 16,
                "memory_gb": 64,
                "expected_minutes": 240,
            },
        }
    )

    assert queue == TaskQueue.HEAVY_COMPUTE_QUEUE.value


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


def test_build_params_payload_preserves_flat_params_with_input_files() -> None:
    payload = build_params_payload(
        "task-1",
        {
            "model_choice": "auto",
            "device": "cpu",
            "input_files": {"protein_pdb": "input/protein.pdb"},
        },
        [],
    )

    assert payload["input_files"] == {"protein_pdb": "input/protein.pdb"}
    assert payload["params"] == {"model_choice": "auto", "device": "cpu"}
    assert "model_choice" not in payload


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


@pytest.mark.asyncio
async def test_legacy_ssh_job_ignores_display_input_bindings(tmp_path) -> None:
    """legacy ssh_job 应使用已投影的 input_files，而不是误走标准 request.v1。"""
    task = _build_task("task-legacy-bindings")
    task.extra_data = {"input_bindings": {"protein": "protein-version-1"}}
    task.inputs = SimpleNamespace(
        params={
            "input_files": {"protein_pdb": "input/prepared.pdb"},
            "params": {"model_choice": "auto"},
        },
        file_ids=[],
    )
    config = {
        "type": "ssh_job",
        "host": "gpu-node-01.internal",
        "username": "runner",
        "runner_mode": "shell",
        "remote_base_dir": "/srv/platform-jobs",
        "entrypoint": "/opt/models/platform_run.sh",
    }
    executor = SSHJobExecutor(task, _build_tool_version(config))

    payload = await executor._prepare_params_payload(str(tmp_path), str(tmp_path / "input"))

    assert "request_version" not in payload
    assert payload["input_files"] == {"protein_pdb": "input/prepared.pdb"}
    assert payload["params"] == {"model_choice": "auto"}


@pytest.mark.asyncio
async def test_ssh_job_executor_projects_standard_inputs_to_legacy_file_fields(
    monkeypatch,
    tmp_path,
) -> None:
    """标准 SSH 任务应同时给旧模型脚本提供 input_files 兼容字段。"""
    task = _build_task("task-affinity")
    task.extra_data = {
        "input_bindings": {
            "protein": "protein-version-1",
            "ligand": "ligand-version-1",
        }
    }
    task.inputs = SimpleNamespace(
        params={"complex_id": "1A2B_generated_001", "distance": 5.0},
        file_ids=[],
    )
    config = {
        "type": "ssh_job",
        "host": "gpu-node-01.internal",
        "username": "runner",
        "runner_mode": "shell",
        "remote_base_dir": "/srv/platform-jobs",
        "entrypoint": "/opt/models/platform_run.sh",
        "input_schema": {
            "type": "object",
            "properties": {
                "protein_pdb": {"type": "string", "format": "file"},
                "ligand_pdb": {"type": "string", "format": "file"},
                "distance": {"type": "number"},
            },
        },
        "tool_package_manifest": _v2_affinity_manifest(),
        "variant": "cpu",
        "accelerator": "cpu",
    }
    executor = SSHJobExecutor(task, _build_tool_version(config))

    async def fake_get_async_session():
        yield object()

    class FakeStandardRequest:
        def model_dump(self, mode: str = "json") -> dict:
            return {
                "request_version": "aidd.sciminer/request.v1",
                "task": {
                    "id": "task-affinity",
                    "tool_slug": "msign-affinity-prediction",
                    "tool_version": "1.0.0",
                },
                "inputs": {
                    "protein": {
                        "artifact_version_id": "protein-version-1",
                        "type": "protein_structure@1",
                        "files": {
                            "structure_file": {
                                "path": "input/protein/structure_file.pdb",
                                "sha256": "a" * 64,
                            }
                        },
                    },
                    "ligand": {
                        "artifact_version_id": "ligand-version-1",
                        "type": "ligand_structure@1",
                        "files": {
                            "structure_file": {
                                "path": "input/ligand/structure_file.sdf",
                                "sha256": "b" * 64,
                            }
                        },
                    },
                },
                "parameters": {"complex_id": "1A2B_generated_001", "distance": 5.0},
                "execution": {"variant": "cpu", "accelerator": "cpu"},
            }

    async def fake_build_standard_execution_request(*args, **kwargs):
        return FakeStandardRequest()

    monkeypatch.setenv("TASK_WORK_DIR", str(tmp_path))
    monkeypatch.setattr("app.tasks.executors.ssh_job.get_async_session", fake_get_async_session)
    monkeypatch.setattr(
        "app.tasks.executors.ssh_job.build_standard_execution_request",
        fake_build_standard_execution_request,
    )

    bundle = await executor._prepare_local_task_bundle()
    payload = json.loads(Path(bundle["params_path"]).read_text(encoding="utf-8"))

    assert payload["request_version"] == "aidd.sciminer/request.v1"
    assert payload["params"] == {"complex_id": "1A2B_generated_001", "distance": 5.0}
    assert payload["input_files"] == {
        "protein_pdb": "input/protein/structure_file.pdb",
        "ligand_pdb": "input/ligand/structure_file.sdf",
    }


@pytest.mark.asyncio
async def test_ssh_job_executor_projects_molecule_table_to_smiles_csv(
    monkeypatch,
    tmp_path,
) -> None:
    """molecule_table@1 标准输入应能桥接到 MolP-PC 的 smiles_csv。"""
    task = _build_task("task-admet")
    task.extra_data = {"input_bindings": {"molecules": "molecule-table-version-1"}}
    task.inputs = SimpleNamespace(params={"task_groups": ["Absorption"]}, file_ids=[])
    config = {
        "type": "ssh_job",
        "host": "gpu-node-01.internal",
        "username": "runner",
        "runner_mode": "shell",
        "remote_base_dir": "/srv/platform-jobs",
        "entrypoint": "/opt/models/platform_run.sh",
        "input_schema": {
            "type": "object",
            "properties": {
                "smiles_csv": {"type": "string", "format": "file"},
                "device": {"type": "string"},
            },
        },
        "tool_package_manifest": _v2_admet_manifest(),
        "variant": "cpu",
        "accelerator": "cpu",
    }
    executor = SSHJobExecutor(task, _build_tool_version(config))

    async def fake_get_async_session():
        yield object()

    class FakeStandardRequest:
        def model_dump(self, mode: str = "json") -> dict:
            return {
                "request_version": "aidd.sciminer/request.v1",
                "task": {
                    "id": "task-admet",
                    "tool_slug": "molp-pc-property-prediction",
                    "tool_version": "1.0.0",
                },
                "inputs": {
                    "molecules": {
                        "artifact_version_id": "molecule-table-version-1",
                        "type": "molecule_table@1",
                        "files": {
                            "table_file": {
                                "path": "input/molecules/table_file.csv",
                                "sha256": "c" * 64,
                            },
                            "metadata_json": {
                                "path": "input/molecules/metadata_json.json",
                                "sha256": "d" * 64,
                            },
                        },
                    }
                },
                "parameters": {"task_groups": ["Absorption"]},
                "execution": {"variant": "cpu", "accelerator": "cpu"},
            }

    async def fake_build_standard_execution_request(*args, **kwargs):
        return FakeStandardRequest()

    monkeypatch.setenv("TASK_WORK_DIR", str(tmp_path))
    monkeypatch.setattr("app.tasks.executors.ssh_job.get_async_session", fake_get_async_session)
    monkeypatch.setattr(
        "app.tasks.executors.ssh_job.build_standard_execution_request",
        fake_build_standard_execution_request,
    )

    bundle = await executor._prepare_local_task_bundle()
    payload = json.loads(Path(bundle["params_path"]).read_text(encoding="utf-8"))

    assert payload["params"] == {"task_groups": ["Absorption"]}
    assert payload["input_files"] == {"smiles_csv": "input/molecules/table_file.csv"}


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


def test_ssh_transport_streams_remote_log_progress(monkeypatch) -> None:
    """远端命令运行时应能读取新增 run.log 行用于任务中心进度。"""

    class FakeChannel:
        def __init__(self) -> None:
            self.polls = 0

        def exit_status_ready(self) -> bool:
            self.polls += 1
            return self.polls > 1

        def recv_ready(self) -> bool:
            return False

        def recv_stderr_ready(self) -> bool:
            return False

        def recv_exit_status(self) -> int:
            return 0

    class FakeStream:
        def __init__(self, content: bytes = b"") -> None:
            self.channel = FakeChannel()
            self._content = content

        def read(self) -> bytes:
            return self._content

    class FakeClient:
        def exec_command(self, command: str, timeout: int):
            stdout = FakeStream(b"stdout")
            stderr = FakeStream()
            stderr.channel = stdout.channel
            return None, stdout, stderr

    class FakeSFTP:
        def stat(self, remote_path: str):
            return SimpleNamespace(st_size=len(b"[INFO] Loading data\n"))

        def open(self, remote_path: str, mode: str = "r"):
            return BytesIO(b"[INFO] Loading data\n")

    events: list[str] = []
    transport = ParamikoSSHTransport(
        host="host",
        port=22,
        username="user",
        auth_settings={"auth_type": "password", "password": "secret"},
        strict_host_key_checking=False,
        timeout=10,
    )
    transport.client = FakeClient()
    transport.sftp = FakeSFTP()
    result = transport.run_command(
        "echo run",
        timeout=10,
        progress_callback=events.append,
        progress_log_paths=["/remote/output/logs/run.log"],
        progress_poll_interval=0,
    )

    assert result.exit_status == 0
    assert result.stdout == "stdout"
    assert events == ["[INFO] Loading data"]


@pytest.mark.asyncio
async def test_ssh_job_executor_reports_remote_progress_events(monkeypatch, tmp_path) -> None:
    """ssh_job 执行期间应把远端阶段和日志事件推给任务进度回调。"""
    events: list[tuple[float, str]] = []

    async def record_progress(progress: float, message: str) -> None:
        events.append((progress, message))

    config = {
        "type": "ssh_job",
        "host": "gpu-node-01.internal",
        "username": "runner",
        "runner_mode": "shell",
        "remote_base_dir": "/srv/platform-jobs",
        "entrypoint": "/opt/models/platform_run.sh",
    }
    executor = SSHJobExecutor(
        _build_task("task-progress"),
        _build_tool_version(config),
        progress_callback=record_progress,
    )

    async def fake_collect_output_files(download_root: str) -> list[str]:
        return []

    def fake_run_remote_workflow_sync(
        local_bundle,
        remote_paths,
        auth_settings,
        timeout,
        progress_sink,
    ):
        progress_sink(15.0, "远端模型进程已启动")
        progress_sink(35.0, "远端运行中：Start sampling")
        return {
            "exit_status": 0,
            "stdout": "",
            "stderr": "",
            "download_root": str(tmp_path),
            "cleanup_error": None,
        }

    monkeypatch.setenv("TASK_WORK_DIR", str(tmp_path))
    monkeypatch.setattr(executor, "_resolve_auth_settings", lambda: {})
    monkeypatch.setattr(executor, "_run_remote_workflow_sync", fake_run_remote_workflow_sync)
    monkeypatch.setattr(executor, "_collect_output_files", fake_collect_output_files)
    monkeypatch.setattr(executor, "_load_result_json", lambda _download_root: {"success": True})

    await executor.execute()

    assert events == [
        (15.0, "远端模型进程已启动"),
        (35.0, "远端运行中：Start sampling"),
    ]


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
