"""SSH 作业远端命令组装。"""

import shlex
from typing import Any

from app.tasks.executors.errors import TaskExecutionError


def build_remote_exec_command(config: dict[str, Any], task_id: str, remote_paths: dict[str, str]) -> str:
    runner_mode = config.get("runner_mode", "shell")
    if runner_mode not in {"docker_exec", "shell"}:
        raise TaskExecutionError(f"不支持的 ssh_job runner_mode：{runner_mode}")
    command_parts = [
        "bash", config["entrypoint"], "--task-id", task_id, "--input-dir", remote_paths["runtime_input_dir"],
        "--output-dir", remote_paths["runtime_output_dir"], "--params-json", remote_paths["runtime_params_file"],
        "--work-dir", remote_paths["runtime_work_dir"],
    ]
    if config.get("device"):
        command_parts.extend(["--device", str(config["device"])])
    runner_command = " ".join(shlex.quote(item) for item in command_parts)
    exports = [f"export {key}={shlex.quote(str(value))}" for key, value in (config.get("env") or {}).items()]
    shell_script = " && ".join([*exports, runner_command]) if exports else runner_command
    if runner_mode == "docker_exec":
        return " ".join(["docker", "exec", shlex.quote(config["container_name"]), "bash", "-lc", shlex.quote(shell_script)])
    return " ".join(["bash", "-lc", shlex.quote(shell_script)])
