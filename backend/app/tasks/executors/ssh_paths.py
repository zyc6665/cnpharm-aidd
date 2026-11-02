"""SSH 作业远端目录路径推导。"""

import posixpath
from typing import Any

from app.tasks.executors.errors import TaskExecutionError


def build_remote_paths(config: dict[str, Any], task_id: str) -> dict[str, str]:
    host_base_dir = str(config.get("remote_base_dir", "")).rstrip("/")
    if not host_base_dir:
        raise TaskExecutionError("ssh_job 配置缺少 remote_base_dir")
    runtime_base_dir = host_base_dir
    if config.get("runner_mode", "shell") == "docker_exec":
        runtime_base_dir = str(config.get("container_base_dir", host_base_dir)).rstrip("/")
    host_task_dir = posixpath.join(host_base_dir, task_id)
    runtime_task_dir = posixpath.join(runtime_base_dir, task_id)
    input_name = config.get("input_dir_name", "input")
    output_name = config.get("output_dir_name", "output")
    work_name = config.get("work_dir_name", "work")
    return {
        "host_task_dir": host_task_dir,
        "host_input_dir": posixpath.join(host_task_dir, input_name),
        "host_output_dir": posixpath.join(host_task_dir, output_name),
        "host_work_dir": posixpath.join(host_task_dir, work_name),
        "host_params_file": posixpath.join(host_task_dir, "params.json"),
        "runtime_task_dir": runtime_task_dir,
        "runtime_input_dir": posixpath.join(runtime_task_dir, input_name),
        "runtime_output_dir": posixpath.join(runtime_task_dir, output_name),
        "runtime_work_dir": posixpath.join(runtime_task_dir, work_name),
        "runtime_params_file": posixpath.join(runtime_task_dir, "params.json"),
    }
