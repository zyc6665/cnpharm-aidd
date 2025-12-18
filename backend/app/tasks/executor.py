# backend/app/tasks/executor.py
"""任务执行器

根据详细设计说明书 4.2 节实现。
支持三种执行方式：
- remote_api: 调用远程API
- docker_image: 运行Docker容器
- python_script: 执行Python脚本
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import logging

import httpx

from app.models.tasks import TaskStatus
from app.models.tools import ToolType
from app.tasks.state_machine import TaskStateMachine

if TYPE_CHECKING:
    from app.models.tasks import Task
    from app.models.tools import ToolVersion

logger = logging.getLogger(__name__)


class TaskExecutionError(Exception):
    """任务执行错误"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class BaseExecutor(ABC):
    """执行器基类"""

    def __init__(self, task: "Task", tool_version: "ToolVersion"):
        self.task = task
        self.tool_version = tool_version
        self.config = tool_version.config
        self.work_dir: Optional[str] = None

    @abstractmethod
    async def execute(self) -> Dict[str, Any]:
        """执行任务"""
        pass

    def _get_work_dir(self) -> str:
        """获取工作目录"""
        if not self.work_dir:
            base_dir = os.environ.get("TASK_WORK_DIR", "/tmp/tasks")
            self.work_dir = os.path.join(base_dir, str(self.task.id))
            os.makedirs(self.work_dir, exist_ok=True)
            os.makedirs(os.path.join(self.work_dir, "input"), exist_ok=True)
            os.makedirs(os.path.join(self.work_dir, "output"), exist_ok=True)
        return self.work_dir

    def _cleanup_work_dir(self) -> None:
        """清理工作目录"""
        if self.work_dir and os.path.exists(self.work_dir):
            try:
                shutil.rmtree(self.work_dir)
                logger.debug(f"Cleaned up work directory: {self.work_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup work directory: {e}")


class RemoteAPIExecutor(BaseExecutor):
    """远程API执行器"""

    async def execute(self) -> Dict[str, Any]:
        """执行远程API调用"""
        endpoint = self.config.get("endpoint")
        if not endpoint:
            raise TaskExecutionError("Missing endpoint in tool config")

        method = self.config.get("method", "POST").upper()
        headers = self.config.get("headers", {})
        timeout = self.config.get("timeout_sec", 600)

        # 准备请求数据
        request_data = await self._prepare_request_data()

        # 发送HTTP请求
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                logger.info(f"Executing remote API: {method} {endpoint}")

                if method == "POST":
                    response = await client.post(
                        endpoint,
                        json=request_data,
                        headers=headers
                    )
                elif method == "GET":
                    response = await client.get(
                        endpoint,
                        params=self._flatten_params(request_data),
                        headers=headers
                    )
                else:
                    raise TaskExecutionError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                result = response.json()

                # 处理输出文件
                if "output_files" in result:
                    uploaded_files = await self._process_output_files(result["output_files"])
                    result["output_file_ids"] = uploaded_files

                return {
                    "success": True,
                    "result": result,
                    "execution_time": timeout
                }

            except httpx.HTTPStatusError as e:
                raise TaskExecutionError(
                    f"API returned error: {e.response.status_code}",
                    details={"response_text": e.response.text[:500]}
                )
            except httpx.TimeoutException:
                raise TaskExecutionError("API request timeout")
            except httpx.ConnectError as e:
                raise TaskExecutionError(f"Failed to connect to API: {str(e)}")
            except Exception as e:
                raise TaskExecutionError(f"API request failed: {str(e)}")

    async def _prepare_request_data(self) -> Dict[str, Any]:
        """准备请求数据"""
        request_data = {
            "task_id": str(self.task.id),
            "params": {}
        }

        # 获取任务输入参数
        if self.task.inputs:
            request_data["params"] = self.task.inputs.params or {}

            # 下载输入文件
            if self.task.inputs.file_ids:
                files = await self._download_input_files()
                request_data["files"] = files

        return request_data

    async def _download_input_files(self) -> List[str]:
        """下载输入文件到本地"""
        from app.storage.factory import get_storage

        file_paths = []
        work_dir = self._get_work_dir()
        storage = get_storage()

        for file_id in self.task.inputs.file_ids:
            try:
                # 这里需要从数据库获取文件信息并下载
                # 暂时返回文件ID列表
                file_paths.append(file_id)
            except Exception as e:
                logger.error(f"Failed to download file {file_id}: {e}")

        return file_paths

    async def _process_output_files(self, output_files: List[Dict]) -> List[str]:
        """处理输出文件"""
        # 上传输出文件到存储
        uploaded_ids = []
        for file_info in output_files:
            # 实际实现需要上传文件到存储
            uploaded_ids.append(str(uuid.uuid4()))
        return uploaded_ids

    def _flatten_params(self, data: Dict[str, Any]) -> Dict[str, str]:
        """将嵌套参数扁平化（用于GET请求）"""
        import json
        flat = {}
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                flat[key] = json.dumps(value)
            else:
                flat[key] = str(value)
        return flat


class DockerExecutor(BaseExecutor):
    """Docker容器执行器"""

    async def execute(self) -> Dict[str, Any]:
        """执行Docker容器任务"""
        image = self.config.get("image")
        if not image:
            raise TaskExecutionError("Missing image in tool config")

        command = self.config.get("command", [])
        timeout = self.config.get("timeout_sec", 600)
        gpu_required = self.config.get("gpu_required", False)

        # 准备工作目录
        work_dir = self._get_work_dir()
        await self._prepare_input_files()

        # 构建Docker运行命令
        docker_cmd = self._build_docker_command(image, command, work_dir, gpu_required)

        try:
            logger.info(f"Executing Docker container: {image}")
            logger.debug(f"Docker command: {' '.join(docker_cmd)}")

            # 执行命令
            process = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=work_dir
                )
            )

            if process.returncode != 0:
                raise TaskExecutionError(
                    f"Docker execution failed with code {process.returncode}",
                    details={
                        "stderr": process.stderr[:1000] if process.stderr else "",
                        "stdout": process.stdout[:1000] if process.stdout else ""
                    }
                )

            # 解析输出
            output = self._parse_docker_output(process.stdout)

            # 收集输出文件
            output_files = await self._collect_output_files()
            if output_files:
                output["output_file_ids"] = output_files

            return {
                "success": True,
                "result": output,
                "stdout": process.stdout,
                "stderr": process.stderr
            }

        except subprocess.TimeoutExpired:
            raise TaskExecutionError("Docker execution timeout")
        except Exception as e:
            if isinstance(e, TaskExecutionError):
                raise
            raise TaskExecutionError(f"Docker execution error: {str(e)}")
        finally:
            self._cleanup_work_dir()

    def _build_docker_command(
        self,
        image: str,
        command: List[str],
        work_dir: str,
        gpu_required: bool
    ) -> List[str]:
        """构建Docker运行命令"""
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{work_dir}:/workspace",
            "-w", "/workspace",
            "--network", "none",  # 安全：禁用网络
            "--memory", self.config.get("memory_limit", "4g"),
            "--cpus", str(self.config.get("cpu_limit", 2)),
        ]

        # GPU支持
        if gpu_required:
            gpu_config = self.config.get("gpu_config", {})
            gpu_count = gpu_config.get("count", "all")
            docker_cmd.extend(["--gpus", str(gpu_count)])

        # 环境变量
        env_vars = self.config.get("env", {})
        for key, value in env_vars.items():
            docker_cmd.extend(["-e", f"{key}={value}"])

        docker_cmd.append(image)

        # 添加命令参数
        if command:
            docker_cmd.extend(command)

        # 添加任务参数
        if self.task.inputs and self.task.inputs.params:
            import json
            params_json = json.dumps(self.task.inputs.params)
            docker_cmd.append(params_json)

        return docker_cmd

    async def _prepare_input_files(self) -> None:
        """准备输入文件"""
        if not self.task.inputs or not self.task.inputs.file_ids:
            return

        work_dir = self._get_work_dir()
        input_dir = os.path.join(work_dir, "input")

        # 下载文件到输入目录
        # 实际实现需要从存储下载
        pass

    async def _collect_output_files(self) -> List[str]:
        """收集输出文件"""
        work_dir = self._get_work_dir()
        output_dir = os.path.join(work_dir, "output")

        if not os.path.exists(output_dir):
            return []

        uploaded_ids = []
        for filename in os.listdir(output_dir):
            file_path = os.path.join(output_dir, filename)
            if os.path.isfile(file_path):
                # 实际实现需要上传到存储
                uploaded_ids.append(str(uuid.uuid4()))

        return uploaded_ids

    def _parse_docker_output(self, stdout: str) -> Dict[str, Any]:
        """解析Docker输出"""
        import json

        # 尝试解析JSON输出
        try:
            # 查找JSON输出标记
            if "OUTPUT_JSON:" in stdout:
                json_start = stdout.index("OUTPUT_JSON:") + len("OUTPUT_JSON:")
                json_str = stdout[json_start:].strip().split("\n")[0]
                return json.loads(json_str)

            # 尝试直接解析最后一行
            lines = stdout.strip().split("\n")
            for line in reversed(lines):
                try:
                    return json.loads(line)
                except:
                    continue

            # 返回原始输出
            return {"raw_output": stdout}

        except Exception:
            return {"raw_output": stdout}


class PythonScriptExecutor(BaseExecutor):
    """Python脚本执行器"""

    async def execute(self) -> Dict[str, Any]:
        """执行Python脚本"""
        script_path = self.config.get("script_path")
        script_content = self.config.get("script_content")
        timeout = self.config.get("timeout_sec", 600)

        if not script_path and not script_content:
            raise TaskExecutionError("Missing script_path or script_content in tool config")

        work_dir = self._get_work_dir()

        try:
            # 准备脚本
            if script_content:
                script_file = os.path.join(work_dir, "script.py")
                with open(script_file, "w") as f:
                    f.write(script_content)
                script_path = script_file

            # 准备参数
            import json
            params_file = os.path.join(work_dir, "params.json")
            params = self.task.inputs.params if self.task.inputs else {}
            with open(params_file, "w") as f:
                json.dump(params, f)

            # 执行脚本
            python_cmd = [
                "python", script_path,
                "--params-file", params_file,
                "--output-dir", os.path.join(work_dir, "output")
            ]

            logger.info(f"Executing Python script: {script_path}")

            process = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    python_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=work_dir,
                    env={**os.environ, "PYTHONPATH": work_dir}
                )
            )

            if process.returncode != 0:
                raise TaskExecutionError(
                    f"Python script failed with code {process.returncode}",
                    details={"stderr": process.stderr[:1000] if process.stderr else ""}
                )

            # 解析输出
            output = self._parse_script_output(work_dir, process.stdout)

            return {
                "success": True,
                "result": output,
                "stdout": process.stdout,
                "stderr": process.stderr
            }

        except subprocess.TimeoutExpired:
            raise TaskExecutionError("Python script execution timeout")
        except Exception as e:
            if isinstance(e, TaskExecutionError):
                raise
            raise TaskExecutionError(f"Python script execution error: {str(e)}")
        finally:
            self._cleanup_work_dir()

    def _parse_script_output(self, work_dir: str, stdout: str) -> Dict[str, Any]:
        """解析脚本输出"""
        import json

        # 检查输出文件
        output_file = os.path.join(work_dir, "output", "result.json")
        if os.path.exists(output_file):
            with open(output_file, "r") as f:
                return json.load(f)

        # 尝试解析stdout
        try:
            return json.loads(stdout)
        except:
            return {"raw_output": stdout}


class TaskExecutor:
    """任务执行器工厂

    根据工具类型选择合适的执行器执行任务。
    """

    EXECUTORS = {
        ToolType.REMOTE_API.value: RemoteAPIExecutor,
        ToolType.DOCKER_IMAGE.value: DockerExecutor,
        ToolType.PYTHON_SCRIPT.value: PythonScriptExecutor,
        "remote_api": RemoteAPIExecutor,
        "docker_image": DockerExecutor,
        "python_script": PythonScriptExecutor,
    }

    def __init__(self, task: "Task", tool_version: "ToolVersion"):
        self.task = task
        self.tool_version = tool_version
        self.config = tool_version.config

    def _get_executor(self) -> BaseExecutor:
        """获取执行器实例"""
        executor_type = self.config.get("type")
        if not executor_type:
            raise TaskExecutionError("Missing type in tool config")

        executor_class = self.EXECUTORS.get(executor_type)
        if not executor_class:
            raise TaskExecutionError(f"Unsupported executor type: {executor_type}")

        return executor_class(self.task, self.tool_version)

    async def execute(self) -> Dict[str, Any]:
        """执行任务

        Returns:
            Dict[str, Any]: 执行结果
        """
        executor = self._get_executor()

        try:
            # 更新任务状态为运行中
            TaskStateMachine.start(self.task, progress_message="任务开始执行")

            # 执行任务
            result = await executor.execute()

            # 更新任务状态为成功
            TaskStateMachine.complete(self.task, success=True, progress_message="任务执行成功")

            return result

        except TaskExecutionError as e:
            # 执行失败
            logger.error(f"Task {self.task.id} execution failed: {e.message}")
            TaskStateMachine.complete(
                self.task,
                success=False,
                error_message=e.message,
                progress_message="任务执行失败"
            )
            raise

        except Exception as e:
            # 未知错误
            logger.exception(f"Task {self.task.id} unexpected error: {e}")
            TaskStateMachine.complete(
                self.task,
                success=False,
                error_message=str(e),
                progress_message="任务执行发生未知错误"
            )
            raise TaskExecutionError(f"Unexpected error: {str(e)}")

    async def execute_with_progress(
        self,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """执行任务并报告进度

        Args:
            progress_callback: 进度回调函数，接收(progress, message)参数

        Returns:
            Dict[str, Any]: 执行结果
        """
        async def report_progress(progress: float, message: str):
            """报告进度"""
            TaskStateMachine.update_progress(self.task, progress, message)
            if progress_callback:
                await progress_callback(progress, message)

        executor = self._get_executor()

        try:
            await report_progress(0, "任务准备中")
            TaskStateMachine.start(self.task)

            await report_progress(10, "任务开始执行")
            result = await executor.execute()

            await report_progress(100, "任务执行完成")
            TaskStateMachine.complete(self.task, success=True)

            return result

        except TaskExecutionError as e:
            logger.error(f"Task {self.task.id} execution failed: {e.message}")
            TaskStateMachine.complete(
                self.task,
                success=False,
                error_message=e.message
            )
            raise

        except Exception as e:
            logger.exception(f"Task {self.task.id} unexpected error")
            TaskStateMachine.complete(
                self.task,
                success=False,
                error_message=str(e)
            )
            raise TaskExecutionError(f"Unexpected error: {str(e)}")
