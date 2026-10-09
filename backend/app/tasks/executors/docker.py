"""Docker 工具执行器。"""

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.database.session import get_async_session
from app.files.content import ensure_local_file
from app.models.files import File as FileModel
from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.docker_output import parse_docker_output
from app.tasks.executors.docker_security import validate_docker_execution_inputs
from app.tasks.executors.errors import TaskExecutionError

logger = logging.getLogger(__name__)


class DockerExecutor(BaseExecutor):
    """在受限 Docker 容器中执行工具。"""

    async def execute(self) -> dict[str, Any]:
        image = self.config.get("image")
        if not image:
            raise TaskExecutionError("Missing image in tool config")
        command = self.config.get("command", [])
        timeout = self.config.get("timeout_sec", 600)
        work_dir = self._get_work_dir()
        await self._prepare_input_files()
        docker_cmd = self._build_docker_command(
            image, command, work_dir, self.config.get("gpu_required", False)
        )
        try:
            process = await asyncio.to_thread(
                subprocess.run,
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=work_dir,
            )
            if process.returncode != 0:
                raise TaskExecutionError(
                    f"Docker execution failed with code {process.returncode}",
                    details={"stderr": (process.stderr or "")[:1000], "stdout": (process.stdout or "")[:1000]},
                )
            output = self._load_output_result(process.stdout)
            output_files = await self._collect_output_files()
            if output_files:
                output["output_file_ids"] = output_files
            return {"success": True, "result": output, "stdout": process.stdout, "stderr": process.stderr}
        except subprocess.TimeoutExpired as exc:
            raise TaskExecutionError("Docker execution timeout") from exc
        except TaskExecutionError:
            raise
        except Exception as exc:
            raise TaskExecutionError(f"Docker execution error: {exc}") from exc
        finally:
            self._cleanup_work_dir()

    def _build_docker_command(self, image: str, command: list[str], work_dir: str, gpu_required: bool) -> list[str]:
        task_params = self.task.inputs.params if self.task.inputs else None
        validate_docker_execution_inputs(image, command, task_params)
        docker_cmd = [
            "docker", "run", "--rm", "-v", f"{work_dir}:/workspace", "-w", "/workspace",
            "--network", "none", "--security-opt", "no-new-privileges:true", "--cap-drop", "ALL",
            "--pids-limit", "256", "--memory", self.config.get("memory_limit", "4g"),
            "--cpus", str(self.config.get("cpu_limit", 2)),
        ]
        if gpu_required:
            gpu_config = self.config.get("gpu_config") or {}
            gpu_device = gpu_config.get("device")
            gpu_request = (
                f"device={gpu_device}"
                if gpu_device is not None
                else str(gpu_config.get("count", "all"))
            )
            docker_cmd.extend(["--gpus", gpu_request])
        for key, value in self.config.get("env", {}).items():
            docker_cmd.extend(["-e", f"{key}={value}"])
        docker_cmd.append(image)
        docker_cmd.extend(command)
        if task_params:
            docker_cmd.append(json.dumps(task_params))
        return docker_cmd

    async def _prepare_input_files(self) -> None:
        if not self.task.inputs or not self.task.inputs.file_ids:
            return
        input_dir = os.path.join(self._get_work_dir(), "input")
        async for session in get_async_session():
            try:
                for file_id in self.task.inputs.file_ids:
                    file_record = (await session.execute(select(FileModel).where(FileModel.id == file_id))).scalar_one_or_none()
                    if not file_record:
                        logger.warning("Input file %s not found, skipping", file_id)
                        continue
                    destination = Path(input_dir) / file_record.filename
                    try:
                        await ensure_local_file(file_record, destination)
                    except FileNotFoundError as exc:
                        raise TaskExecutionError(
                            f"Input file {file_record.filename} not found in storage"
                        ) from exc
                break
            except TaskExecutionError:
                raise
            except Exception as exc:
                raise TaskExecutionError(f"Failed to prepare input files: {exc}") from exc

    async def _collect_output_files(self) -> list[str]:
        output_dir = os.path.join(self._get_work_dir(), "output")
        if not os.path.exists(output_dir):
            return []
        source_paths = [
            os.path.join(root, filename)
            for root, _dirs, filenames in os.walk(output_dir)
            for filename in filenames
        ]
        return await super()._collect_output_files(
            source_paths,
            output_root=output_dir,
            filename_builder=lambda _source, relative: relative.replace(os.sep, "__"),
            file_meta_builder=lambda _source, relative: {"relative_path": relative},
            skip_names={"result.json"},
        )

    def _load_output_result(self, stdout: str) -> dict[str, Any]:
        result_path = os.path.join(self._get_work_dir(), "output", "result.json")
        if os.path.exists(result_path):
            with open(result_path, "r", encoding="utf-8") as result_file:
                return json.load(result_file)
        return parse_docker_output(stdout)
