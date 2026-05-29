# backend/app/tasks/executor.py
"""任务执行器

根据详细设计说明书 4.2 节实现。
支持四种执行方式：
- remote_api: 调用远程API
- docker_image: 运行Docker容器
- python_script: 执行Python脚本
- ssh_job: 通过 SSH 调用远端统一入口脚本
"""

import asyncio
import glob
import hashlib
import json
import mimetypes
import os
import posixpath
import re
import shlex
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
from app.tasks.ssh_transport import ParamikoSSHTransport

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
        request_data = {}

        # 获取任务输入参数
        if self.task.inputs:
            input_params = self.task.inputs.params or {}

            # 检查是否需要包装为 request 对象（用于某些 API 如 LVPocket）
            request_wrapper = self.config.get("request_wrapper", False)

            # 分离 params 和 input_files
            # 如果输入参数包含 params 和 input_files，直接使用
            if "params" in input_params and "input_files" in input_params:
                inner_data = {
                    "task_id": str(self.task.id),
                    "params": input_params["params"],
                    "input_files": input_params["input_files"]
                }

                if request_wrapper:
                    # 包装为 request 对象（LVPocket API 格式）
                    request_data = inner_data
                else:
                    request_data = inner_data
            else:
                # 否则将所有参数放在 params 下（向后兼容）
                request_data = {
                    "task_id": str(self.task.id),
                    "params": input_params
                }

            # 处理文件ID（如果有上传的文件）
            if self.task.inputs.file_ids:
                files = await self._download_input_files()
                request_data["files"] = files

        return request_data

    async def _download_input_files(self) -> List[str]:
        """下载输入文件到本地"""
        from sqlalchemy import select
        from app.models.files import File as FileModel
        from app.database.session import get_async_session

        file_paths = []
        work_dir = self._get_work_dir()
        input_dir = os.path.join(work_dir, "input")
        os.makedirs(input_dir, exist_ok=True)

        async for session in get_async_session():
            try:
                for file_id in self.task.inputs.file_ids:
                    # 查询文件记录
                    result = await session.execute(
                        select(FileModel).where(FileModel.id == file_id)
                    )
                    file_record = result.scalar_one_or_none()

                    if not file_record:
                        logger.warning(f"Input file {file_id} not found, skipping")
                        continue

                    # 检查源文件是否存在
                    if not file_record.storage_path or not os.path.exists(file_record.storage_path):
                        logger.error(f"Input file {file_record.filename} not found in storage")
                        continue

                    # 复制文件到输入目录
                    dst_path = os.path.join(input_dir, file_record.filename)
                    shutil.copy2(file_record.storage_path, dst_path)
                    file_paths.append(dst_path)
                    logger.info(f"Downloaded input file: {file_record.filename}")

                break
            except Exception as e:
                logger.error(f"Failed to download input files: {e}")
                raise TaskExecutionError(f"Failed to download input files: {str(e)}")

        return file_paths

    async def _process_output_files(self, output_files: List[Dict]) -> List[str]:
        """处理输出文件"""
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.models.files import File as FileModel, FileSourceType
        from app.database.session import get_async_session
        import hashlib

        uploaded_ids = []

        async for session in get_async_session():
            try:
                for file_info in output_files:
                    url = file_info.get("url")
                    # 兼容 "name" 和 "filename" 两种字段名
                    filename = file_info.get("name") or file_info.get("filename", f"output_{uuid.uuid4()}.dat")

                    if not url:
                        logger.warning(f"Output file {filename} missing URL, skipping")
                        continue

                    try:
                        # 从远程URL下载文件
                        async with httpx.AsyncClient(timeout=300) as client:
                            response = await client.get(url)
                            response.raise_for_status()
                            content = response.content

                        # 计算文件信息
                        sha256_hash = hashlib.sha256(content).hexdigest()
                        file_size = len(content)
                        content_type = response.headers.get("content-type", "application/octet-stream")

                        # 创建文件记录
                        file_record = FileModel(
                            filename=filename,
                            content_type=content_type,
                            size_bytes=file_size,
                            sha256=sha256_hash,
                            source_type=FileSourceType.TOOL_OUTPUT.value,
                            owner_id=self.task.user_id,
                            is_public=False,
                            is_permanent=False
                        )

                        session.add(file_record)
                        await session.flush()

                        # 保存到存储
                        from app.api.v1.files import get_file_path
                        storage_path = get_file_path(file_record.id, filename)
                        storage_path.parent.mkdir(parents=True, exist_ok=True)

                        # 写入文件
                        with open(storage_path, "wb") as f:
                            f.write(content)

                        # 更新存储路径
                        file_record.storage_path = str(storage_path)
                        await session.flush()

                        uploaded_ids.append(file_record.id)
                        logger.info(f"Processed output file from {url} -> {file_record.id}")

                    except httpx.HTTPError as e:
                        logger.error(f"Failed to download output file from {url}: {e}")
                        continue
                    except Exception as e:
                        logger.error(f"Failed to process output file {filename}: {e}")
                        continue

                await session.commit()
                break
            except Exception as e:
                logger.error(f"Failed to process output files: {e}")
                await session.rollback()
                raise TaskExecutionError(f"Failed to process output files: {str(e)}")

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

        # 从数据库获取文件记录并复制到工作目录
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.models.files import File as FileModel
        from app.database.session import get_async_session

        async for session in get_async_session():
            try:
                for file_id in self.task.inputs.file_ids:
                    # 查询文件记录
                    result = await session.execute(
                        select(FileModel).where(FileModel.id == file_id)
                    )
                    file_record = result.scalar_one_or_none()

                    if not file_record:
                        logger.warning(f"Input file {file_id} not found, skipping")
                        continue

                    # 检查源文件是否存在
                    if not file_record.storage_path or not os.path.exists(file_record.storage_path):
                        raise TaskExecutionError(
                            f"Input file {file_record.filename} not found in storage",
                            details={"file_id": file_id, "storage_path": file_record.storage_path}
                        )

                    # 复制文件到输入目录
                    dst_path = os.path.join(input_dir, file_record.filename)
                    try:
                        shutil.copy2(file_record.storage_path, dst_path)
                        logger.info(f"Prepared input file: {file_record.filename}")
                    except Exception as e:
                        raise TaskExecutionError(
                            f"Failed to prepare input file {file_record.filename}: {str(e)}",
                            details={"file_id": file_id, "error": str(e)}
                        )
                break
            except Exception as e:
                if isinstance(e, TaskExecutionError):
                    raise
                raise TaskExecutionError(f"Failed to prepare input files: {str(e)}")

    async def _collect_output_files(self) -> List[str]:
        """收集输出文件"""
        work_dir = self._get_work_dir()
        output_dir = os.path.join(work_dir, "output")

        if not os.path.exists(output_dir):
            return []

        from sqlalchemy.ext.asyncio import AsyncSession
        from app.models.files import File as FileModel, FileSourceType
        from app.database.session import get_async_session
        from pathlib import Path
        import hashlib

        uploaded_ids = []

        async for session in get_async_session():
            try:
                for filename in os.listdir(output_dir):
                    file_path = os.path.join(output_dir, filename)
                    if not os.path.isfile(file_path):
                        continue

                    try:
                        # 读取文件内容并计算SHA256
                        with open(file_path, "rb") as f:
                            content = f.read()

                        sha256_hash = hashlib.sha256(content).hexdigest()
                        file_size = len(content)

                        # 创建文件记录
                        file_record = FileModel(
                            filename=filename,
                            content_type="application/octet-stream",  # 通用类型
                            size_bytes=file_size,
                            sha256=sha256_hash,
                            source_type=FileSourceType.TOOL_OUTPUT.value,
                            owner_id=self.task.user_id,
                            is_public=False,
                            is_permanent=False  # 任务输出文件临时存储
                        )

                        session.add(file_record)
                        await session.flush()

                        # 保存到存储（使用与上传API相同的逻辑）
                        from app.api.v1.files import get_file_path
                        storage_path = get_file_path(file_record.id, filename)
                        storage_path.parent.mkdir(parents=True, exist_ok=True)

                        # 复制文件到存储位置
                        shutil.copy2(file_path, str(storage_path))

                        # 更新存储路径
                        file_record.storage_path = str(storage_path)
                        await session.flush()

                        uploaded_ids.append(file_record.id)
                        logger.info(f"Collected output file: {filename} -> {file_record.id}")

                    except Exception as e:
                        logger.error(f"Failed to collect output file {filename}: {e}")
                        continue

                await session.commit()
                break
            except Exception as e:
                logger.error(f"Failed to collect output files: {e}")
                await session.rollback()
                raise TaskExecutionError(f"Failed to collect output files: {str(e)}")

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

    async def _collect_output_files(self) -> List[str]:
        """收集输出文件"""
        work_dir = self._get_work_dir()
        output_dir = os.path.join(work_dir, "output")

        if not os.path.exists(output_dir):
            return []

        from sqlalchemy.ext.asyncio import AsyncSession
        from app.models.files import File as FileModel, FileSourceType
        from app.database.session import get_async_session
        from pathlib import Path
        import hashlib

        uploaded_ids = []

        async for session in get_async_session():
            try:
                for filename in os.listdir(output_dir):
                    file_path = os.path.join(output_dir, filename)

                    # 跳过 result.json（这是结果数据，不是输出文件）
                    if filename == "result.json" or not os.path.isfile(file_path):
                        continue

                    try:
                        # 读取文件内容并计算SHA256
                        with open(file_path, "rb") as f:
                            content = f.read()

                        sha256_hash = hashlib.sha256(content).hexdigest()
                        file_size = len(content)

                        # 创建文件记录
                        file_record = FileModel(
                            filename=filename,
                            content_type="application/octet-stream",
                            size_bytes=file_size,
                            sha256=sha256_hash,
                            source_type=FileSourceType.TOOL_OUTPUT.value,
                            owner_id=self.task.user_id,
                            is_public=False,
                            is_permanent=False
                        )

                        session.add(file_record)
                        await session.flush()

                        # 保存到存储
                        from app.api.v1.files import get_file_path
                        storage_path = get_file_path(file_record.id, filename)
                        storage_path.parent.mkdir(parents=True, exist_ok=True)

                        # 复制文件到存储位置
                        shutil.copy2(file_path, str(storage_path))

                        # 更新存储路径
                        file_record.storage_path = str(storage_path)
                        await session.flush()

                        uploaded_ids.append(file_record.id)
                        logger.info(f"Collected output file: {filename} -> {file_record.id}")

                    except Exception as e:
                        logger.error(f"Failed to collect output file {filename}: {e}")
                        continue

                await session.commit()
                break
            except Exception as e:
                logger.error(f"Failed to collect output files: {e}")
                await session.rollback()
                raise TaskExecutionError(f"Failed to collect output files: {str(e)}")

        return uploaded_ids


class SSHJobExecutor(BaseExecutor):
    """SSH 作业执行器。"""

    SUPPORTED_RUNNER_MODES = {"docker_exec", "shell"}

    async def execute(self) -> Dict[str, Any]:
        """通过 SSH 上传输入、调用远端脚本并拉回输出。"""
        timeout = self.config.get("timeout_sec", 3600)
        local_bundle = await self._prepare_local_task_bundle()
        remote_paths = self._build_remote_paths()
        auth_settings = self._resolve_auth_settings()

        try:
            remote_result = await asyncio.to_thread(
                self._run_remote_workflow_sync,
                local_bundle,
                remote_paths,
                auth_settings,
                timeout,
            )

            download_root = remote_result.get("download_root")

            result = (
                self._load_result_json(download_root)
                if download_root
                else {
                    "success": False,
                    "message": "SSH job execution failed before output/result.json was produced",
                }
            )
            output_file_ids = await self._collect_output_files(download_root)
            if output_file_ids:
                result["output_file_ids"] = output_file_ids

            cleanup_error = remote_result.get("cleanup_error")
            if cleanup_error:
                logger.warning("Failed to cleanup remote SSH job directory: %s", cleanup_error)

            if remote_result["exit_status"] != 0:
                raise TaskExecutionError(
                    f"SSH job execution failed with code {remote_result['exit_status']}",
                    details={
                        "stdout": (remote_result.get("stdout") or "")[:1000],
                        "stderr": (remote_result.get("stderr") or "")[:1000],
                        "remote_host": self.config.get("host"),
                        "result": result,
                    },
                )

            if not result.get("success", True):
                error = result.get("error") or {}
                raise TaskExecutionError(
                    result.get("message") or error.get("code") or "SSH job reported failure",
                    details={"result": result},
                )

            return {
                "success": True,
                "result": result,
                "output_file_ids": output_file_ids,
                "stdout": remote_result.get("stdout", ""),
                "stderr": remote_result.get("stderr", ""),
            }

        except TimeoutError:
            raise TaskExecutionError("SSH job execution timeout")
        except Exception as e:
            if isinstance(e, TaskExecutionError):
                raise
            raise TaskExecutionError(f"SSH job execution error: {str(e)}")
        finally:
            self._cleanup_work_dir()

    def _run_remote_workflow_sync(
        self,
        local_bundle: Dict[str, str],
        remote_paths: Dict[str, str],
        auth_settings: Dict[str, Optional[str]],
        timeout: int,
    ) -> Dict[str, Any]:
        """在线程中执行完整的 SSH/SFTP 工作流。"""
        transport = ParamikoSSHTransport(
            host=self.config["host"],
            port=int(self.config.get("port", 22)),
            username=self.config["username"],
            auth_settings=auth_settings,
            strict_host_key_checking=self.config.get("strict_host_key_checking", True),
            timeout=min(timeout, 60),
        )
        cleanup_error: Optional[str] = None
        workflow_result: Optional[Dict[str, Any]] = None

        try:
            transport.connect()
            for remote_dir in (
                remote_paths["host_task_dir"],
                remote_paths["host_input_dir"],
                remote_paths["host_output_dir"],
                remote_paths["host_work_dir"],
            ):
                transport.ensure_dir(remote_dir)

            transport.upload_tree(local_bundle["input_dir"], remote_paths["host_input_dir"])
            transport.upload_file(local_bundle["params_path"], remote_paths["host_params_file"])

            command_result = transport.run_command(
                self._build_remote_exec_command(remote_paths),
                timeout=timeout,
            )

            download_root: Optional[str] = None
            local_output_dir = os.path.join(local_bundle["download_root"], "output")
            try:
                transport.download_tree(remote_paths["host_output_dir"], local_output_dir)
                download_root = local_bundle["download_root"]
            except Exception as exc:
                if command_result.exit_status == 0:
                    raise TaskExecutionError(
                        "Failed to download SSH job outputs",
                        details={"error": str(exc), "remote_output_dir": remote_paths["host_output_dir"]},
                    ) from exc
                logger.warning(
                    "Failed to download SSH job outputs after remote failure: %s",
                    str(exc)[:500],
                )

            workflow_result = {
                "exit_status": command_result.exit_status,
                "stdout": command_result.stdout,
                "stderr": command_result.stderr,
                "download_root": download_root,
            }
        finally:
            if self.config.get("cleanup_remote", True):
                try:
                    transport.remove_tree(remote_paths["host_task_dir"])
                except Exception as exc:
                    cleanup_error = str(exc)
            transport.close()

        if workflow_result is None:
            raise TaskExecutionError("SSH job execution produced no workflow result")

        workflow_result["cleanup_error"] = cleanup_error
        return workflow_result

    async def _prepare_local_task_bundle(self) -> Dict[str, str]:
        """准备本地待上传任务包。"""
        work_dir = self._get_work_dir()
        input_dir = os.path.join(work_dir, "input")
        params_path = os.path.join(work_dir, "params.json")
        download_root = os.path.join(work_dir, "download")
        os.makedirs(download_root, exist_ok=True)

        staged_files = await self._prepare_input_files(input_dir)
        params_payload = self._build_params_payload(staged_files)
        with open(params_path, "w", encoding="utf-8") as params_file:
            json.dump(params_payload, params_file, ensure_ascii=False, indent=2)

        return {
            "work_dir": work_dir,
            "input_dir": input_dir,
            "params_path": params_path,
            "download_root": download_root,
        }

    async def _prepare_input_files(self, input_dir: str) -> List[Dict[str, str]]:
        """准备输入文件并返回逻辑路径信息。"""
        if not self.task.inputs or not self.task.inputs.file_ids:
            return []

        from sqlalchemy import select
        from app.models.files import File as FileModel
        from app.database.session import get_async_session

        staged_files: List[Dict[str, str]] = []

        async for session in get_async_session():
            try:
                for file_id in self.task.inputs.file_ids:
                    result = await session.execute(
                        select(FileModel).where(FileModel.id == file_id)
                    )
                    file_record = result.scalar_one_or_none()

                    if not file_record:
                        logger.warning(f"Input file {file_id} not found, skipping")
                        continue

                    if not file_record.storage_path or not os.path.exists(file_record.storage_path):
                        raise TaskExecutionError(
                            f"Input file {file_record.filename} not found in storage",
                            details={"file_id": file_id, "storage_path": file_record.storage_path},
                        )

                    destination_path = os.path.join(input_dir, file_record.filename)
                    shutil.copy2(file_record.storage_path, destination_path)
                    staged_files.append(
                        {
                            "file_id": str(file_id),
                            "filename": file_record.filename,
                            "relative_path": posixpath.join("input", file_record.filename),
                            "local_path": destination_path,
                        }
                    )
                    logger.info(f"Prepared SSH input file: {file_record.filename}")
                break
            except Exception as e:
                if isinstance(e, TaskExecutionError):
                    raise
                raise TaskExecutionError(f"Failed to prepare SSH input files: {str(e)}")

        return staged_files

    def _build_params_payload(self, staged_files: List[Dict[str, str]]) -> Dict[str, Any]:
        """构建统一的 params.json 内容。"""
        raw_params = self.task.inputs.params if self.task.inputs else {}
        raw_params = raw_params or {}

        if isinstance(raw_params, dict) and (
            "params" in raw_params or "input_files" in raw_params
        ):
            payload = {
                "task_id": str(self.task.id),
                "params": raw_params.get("params", {}),
                "input_files": raw_params.get("input_files", {}),
            }
            extra_fields = {
                key: value
                for key, value in raw_params.items()
                if key not in {"params", "input_files"}
            }
            payload.update(extra_fields)
        else:
            payload = {
                "task_id": str(self.task.id),
                "params": raw_params if isinstance(raw_params, dict) else {},
                "input_files": {},
            }

        if staged_files:
            payload["uploaded_files"] = [
                {
                    "file_id": file_info["file_id"],
                    "filename": file_info["filename"],
                    "path": file_info["relative_path"],
                }
                for file_info in staged_files
            ]
            payload["files"] = [file_info["relative_path"] for file_info in staged_files]

        return payload

    def _build_remote_paths(self) -> Dict[str, str]:
        """构建远端宿主机与运行时路径。"""
        task_id = str(self.task.id)
        host_base_dir = self.config.get("remote_base_dir", "").rstrip("/")
        if not host_base_dir:
            raise TaskExecutionError("Missing remote_base_dir in ssh_job config")

        runner_mode = self.config.get("runner_mode", "shell")
        runtime_base_dir = host_base_dir
        if runner_mode == "docker_exec":
            runtime_base_dir = self.config.get("container_base_dir", host_base_dir).rstrip("/")

        host_task_dir = posixpath.join(host_base_dir, task_id)
        runtime_task_dir = posixpath.join(runtime_base_dir, task_id)

        return {
            "host_task_dir": host_task_dir,
            "host_input_dir": posixpath.join(host_task_dir, self.config.get("input_dir_name", "input")),
            "host_output_dir": posixpath.join(host_task_dir, self.config.get("output_dir_name", "output")),
            "host_work_dir": posixpath.join(host_task_dir, self.config.get("work_dir_name", "work")),
            "host_params_file": posixpath.join(host_task_dir, "params.json"),
            "runtime_task_dir": runtime_task_dir,
            "runtime_input_dir": posixpath.join(runtime_task_dir, self.config.get("input_dir_name", "input")),
            "runtime_output_dir": posixpath.join(runtime_task_dir, self.config.get("output_dir_name", "output")),
            "runtime_work_dir": posixpath.join(runtime_task_dir, self.config.get("work_dir_name", "work")),
            "runtime_params_file": posixpath.join(runtime_task_dir, "params.json"),
        }

    def _resolve_auth_settings(self) -> Dict[str, Optional[str]]:
        """解析 SSH 认证设置。"""
        auth_type = str(self.config.get("auth_type", "key")).lower()
        if auth_type not in {"key", "password"}:
            raise TaskExecutionError(f"Unsupported ssh_job auth_type: {auth_type}")

        auth_label = ""
        key_path: Optional[str] = None
        password: Optional[str] = None

        if auth_type == "key":
            auth_ref = self.config.get("auth_ref")
            if not isinstance(auth_ref, str) or not auth_ref.strip():
                raise TaskExecutionError("Missing auth_ref in ssh_job config")
            auth_label = auth_ref
            key_path = self._resolve_secret_file_path(
                env_var_prefix="SSH_AUTH_REF_",
                directory_env_var="SSH_AUTH_REF_DIR",
                ref_name=auth_ref,
            )
            if not key_path:
                raise TaskExecutionError(
                    f"SSH auth_ref '{auth_ref}' is not configured on worker node",
                    details={"auth_ref": auth_ref},
                )
        else:
            password_ref = self.config.get("password_ref")
            if not isinstance(password_ref, str) or not password_ref.strip():
                raise TaskExecutionError("Missing password_ref in ssh_job config")
            auth_label = password_ref
            password = self._resolve_secret_value(
                env_var_prefix="SSH_PASSWORD_REF_",
                directory_env_var="SSH_PASSWORD_REF_DIR",
                ref_name=password_ref,
            )
            if not password:
                raise TaskExecutionError(
                    f"SSH password_ref '{password_ref}' is not configured on worker node",
                    details={"password_ref": password_ref},
                )

        env_suffix = re.sub(r"[^A-Za-z0-9]+", "_", auth_label).upper()
        known_hosts_path = (
            os.environ.get(f"SSH_KNOWN_HOSTS_{env_suffix}")
            or os.environ.get("SSH_KNOWN_HOSTS")
        )
        if known_hosts_path and not os.path.exists(known_hosts_path):
            raise TaskExecutionError(
                f"SSH known_hosts file does not exist: {known_hosts_path}",
                details={"auth_type": auth_type, "known_hosts_path": known_hosts_path},
            )

        return {
            "auth_type": auth_type,
            "key_path": key_path,
            "password": password,
            "known_hosts_path": known_hosts_path,
        }

    def _resolve_secret_file_path(
        self,
        env_var_prefix: str,
        directory_env_var: str,
        ref_name: str,
    ) -> Optional[str]:
        """解析文件型凭据路径。"""
        if env_var_prefix:
            env_suffix = re.sub(r"[^A-Za-z0-9]+", "_", ref_name).upper()
            candidate_path = os.environ.get(f"{env_var_prefix}{env_suffix}")
            if candidate_path and os.path.exists(candidate_path):
                return candidate_path

        base_dir = os.environ.get(directory_env_var)
        if base_dir:
            candidate = os.path.join(base_dir, ref_name)
            if os.path.exists(candidate):
                return candidate

        return None

    def _resolve_secret_value(
        self,
        env_var_prefix: str,
        directory_env_var: str,
        ref_name: str,
    ) -> Optional[str]:
        """解析字符串型凭据。"""
        env_suffix = re.sub(r"[^A-Za-z0-9]+", "_", ref_name).upper()
        candidate_value = os.environ.get(f"{env_var_prefix}{env_suffix}")
        if isinstance(candidate_value, str) and candidate_value:
            return candidate_value

        file_path = self._resolve_secret_file_path("", directory_env_var, ref_name)
        if file_path:
            with open(file_path, "r", encoding="utf-8") as secret_file:
                return secret_file.read().strip()

        return None

    def _build_command_env(self, auth_settings: Dict[str, Optional[str]]) -> Optional[Dict[str, str]]:
        """为本地 ssh/scp 命令构造附加环境变量。"""
        if auth_settings.get("auth_type") == "password" and auth_settings.get("password"):
            return {"SSHPASS": auth_settings["password"] or ""}
        return None

    def _ensure_ssh_binaries(self, auth_settings: Dict[str, Optional[str]]) -> None:
        """确保 ssh/scp 可用。"""
        required_binaries = ["ssh", "scp"]
        if auth_settings.get("auth_type") == "password":
            required_binaries.append("sshpass")

        for binary_name in required_binaries:
            if shutil.which(binary_name):
                continue
            raise TaskExecutionError(f"Missing required binary for ssh_job: {binary_name}")

    async def _ensure_remote_dirs(
        self,
        auth_settings: Dict[str, Optional[str]],
        remote_paths: Dict[str, str],
    ) -> None:
        """创建远端任务目录。"""
        mkdir_command = "mkdir -p {task} {input_dir} {output_dir} {work_dir}".format(
            task=shlex.quote(remote_paths["host_task_dir"]),
            input_dir=shlex.quote(remote_paths["host_input_dir"]),
            output_dir=shlex.quote(remote_paths["host_output_dir"]),
            work_dir=shlex.quote(remote_paths["host_work_dir"]),
        )
        process = await self._run_local_command(
            self._build_ssh_command(auth_settings, mkdir_command),
            timeout=min(self.config.get("timeout_sec", 3600), 60),
            extra_env=self._build_command_env(auth_settings),
        )
        if process.returncode != 0:
            raise TaskExecutionError(
                "Failed to create remote SSH task directories",
                details={"stderr": (process.stderr or "")[:1000]},
            )

    async def _upload_task_bundle(
        self,
        auth_settings: Dict[str, Optional[str]],
        local_bundle: Dict[str, str],
        remote_paths: Dict[str, str],
    ) -> None:
        """上传输入目录与 params.json。"""
        upload_targets = [
            (local_bundle["input_dir"], f"{self._user_at_host()}:{remote_paths['host_task_dir']}", True),
            (local_bundle["params_path"], f"{self._user_at_host()}:{remote_paths['host_params_file']}", False),
        ]

        for source_path, target_path, recursive in upload_targets:
            process = await self._run_local_command(
                self._build_scp_command(
                    auth_settings=auth_settings,
                    source_path=source_path,
                    target_path=target_path,
                    recursive=recursive,
                ),
                timeout=min(self.config.get("timeout_sec", 3600), 300),
                extra_env=self._build_command_env(auth_settings),
            )
            if process.returncode != 0:
                raise TaskExecutionError(
                    "Failed to upload SSH task bundle",
                    details={
                        "source_path": source_path,
                        "target_path": target_path,
                        "stderr": (process.stderr or "")[:1000],
                    },
                )

    def _build_remote_exec_command(self, remote_paths: Dict[str, str]) -> str:
        """构建远端执行命令。"""
        runner_mode = self.config.get("runner_mode", "shell")
        if runner_mode not in self.SUPPORTED_RUNNER_MODES:
            raise TaskExecutionError(f"Unsupported ssh_job runner_mode: {runner_mode}")

        command_parts = [
            "bash",
            self.config["entrypoint"],
            "--task-id",
            str(self.task.id),
            "--input-dir",
            remote_paths["runtime_input_dir"],
            "--output-dir",
            remote_paths["runtime_output_dir"],
            "--params-json",
            remote_paths["runtime_params_file"],
            "--work-dir",
            remote_paths["runtime_work_dir"],
        ]

        device = self.config.get("device")
        if device:
            command_parts.extend(["--device", str(device)])

        runner_command = " ".join(shlex.quote(item) for item in command_parts)
        env_exports = [
            f"export {key}={shlex.quote(str(value))}"
            for key, value in (self.config.get("env") or {}).items()
        ]
        shell_script = " && ".join([*env_exports, runner_command]) if env_exports else runner_command

        if runner_mode == "docker_exec":
            return " ".join(
                [
                    "docker",
                    "exec",
                    shlex.quote(self.config["container_name"]),
                    "bash",
                    "-lc",
                    shlex.quote(shell_script),
                ]
            )

        return " ".join(
            [
                "bash",
                "-lc",
                shlex.quote(shell_script),
            ]
        )

    async def _download_remote_outputs(
        self,
        auth_settings: Dict[str, Optional[str]],
        remote_paths: Dict[str, str],
        required: bool,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """下载远端 output 目录。"""
        download_root = os.path.join(self._get_work_dir(), "download")
        os.makedirs(download_root, exist_ok=True)

        process = await self._run_local_command(
            self._build_scp_command(
                auth_settings=auth_settings,
                source_path=f"{self._user_at_host()}:{remote_paths['host_output_dir']}",
                target_path=download_root,
                recursive=True,
            ),
            timeout=min(self.config.get("timeout_sec", 3600), 300),
            extra_env=extra_env,
        )

        if process.returncode != 0:
            if required:
                raise TaskExecutionError(
                    "Failed to download SSH job outputs",
                    details={"stderr": (process.stderr or "")[:1000]},
                )
            logger.warning(
                "Failed to download SSH job outputs after remote failure: %s",
                (process.stderr or "")[:500],
            )
            return None

        return download_root

    def _load_result_json(self, download_root: Optional[str]) -> Dict[str, Any]:
        """读取 output/result.json。"""
        if not download_root:
            raise TaskExecutionError("Missing downloaded output directory for ssh_job")

        result_path = os.path.join(download_root, "output", "result.json")
        if not os.path.exists(result_path):
            raise TaskExecutionError(
                "Missing output/result.json from ssh_job",
                details={"download_root": download_root},
            )

        try:
            with open(result_path, "r", encoding="utf-8") as result_file:
                return json.load(result_file)
        except json.JSONDecodeError as exc:
            raise TaskExecutionError(
                f"Invalid output/result.json from ssh_job: {exc}",
                details={"result_path": result_path},
            ) from exc

    async def _collect_output_files(self, download_root: Optional[str]) -> List[str]:
        """收集 SSH 下载回来的日志和产物文件。"""
        if not download_root:
            return []

        output_root = os.path.join(download_root, "output")
        if not os.path.exists(output_root):
            return []

        matched_files = self._expand_output_globs(download_root, output_root)
        if not matched_files:
            return []

        from app.api.v1.files import get_file_path
        from app.database.session import get_async_session
        from app.models.files import File as FileModel, FileSourceType

        uploaded_ids: List[str] = []

        async for session in get_async_session():
            try:
                for file_path in matched_files:
                    relative_path = os.path.relpath(file_path, output_root)
                    if relative_path == "result.json":
                        continue

                    try:
                        with open(file_path, "rb") as output_file:
                            content = output_file.read()

                        file_hash = hashlib.sha256(content).hexdigest()
                        file_size = len(content)
                        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
                        storage_name = relative_path.replace(os.sep, "__")

                        file_record = FileModel(
                            filename=storage_name,
                            content_type=content_type,
                            size_bytes=file_size,
                            sha256=file_hash,
                            source_type=FileSourceType.TOOL_OUTPUT.value,
                            owner_id=self.task.user_id,
                            is_public=False,
                            is_permanent=False,
                            file_meta={"relative_path": relative_path},
                        )
                        session.add(file_record)
                        await session.flush()

                        storage_path = get_file_path(file_record.id, storage_name)
                        storage_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file_path, str(storage_path))

                        file_record.storage_path = str(storage_path)
                        await session.flush()

                        uploaded_ids.append(file_record.id)
                        logger.info(f"Collected SSH output file: {relative_path} -> {file_record.id}")
                    except Exception as exc:
                        logger.error(f"Failed to collect SSH output file {relative_path}: {exc}")
                        continue

                await session.commit()
                break
            except Exception as exc:
                logger.error(f"Failed to collect SSH output files: {exc}")
                await session.rollback()
                raise TaskExecutionError(f"Failed to collect SSH output files: {str(exc)}")

        return uploaded_ids

    def _expand_output_globs(self, download_root: str, output_root: str) -> List[str]:
        """展开 output_globs，默认回收 output 下所有文件。"""
        patterns = self.config.get("output_globs") or ["output/**/*"]
        matched_files: Dict[str, None] = {}

        for pattern in patterns:
            for match_path in glob.glob(os.path.join(download_root, pattern), recursive=True):
                if os.path.isfile(match_path):
                    matched_files[match_path] = None

        if matched_files:
            return list(matched_files.keys())

        for output_path in Path(output_root).rglob("*"):
            if output_path.is_file():
                matched_files[str(output_path)] = None
        return list(matched_files.keys())

    async def _cleanup_remote_task_dir(
        self,
        auth_settings: Optional[Dict[str, Optional[str]]],
        remote_paths: Optional[Dict[str, str]],
    ) -> None:
        """清理远端任务目录。"""
        if not auth_settings or not remote_paths:
            return

        cleanup_command = f"rm -rf {shlex.quote(remote_paths['host_task_dir'])}"
        process = await self._run_local_command(
            self._build_ssh_command(auth_settings, cleanup_command),
            timeout=60,
            extra_env=self._build_command_env(auth_settings),
        )
        if process.returncode != 0:
            raise TaskExecutionError(
                "Failed to cleanup remote ssh_job directory",
                details={"stderr": (process.stderr or "")[:1000]},
            )

    async def _run_local_command(
        self,
        command: List[str],
        timeout: int,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> subprocess.CompletedProcess[str]:
        """在线程池中执行本地命令。"""
        logger.debug(f"Executing local SSH helper command: {' '.join(command)}")
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, **(extra_env or {})},
            ),
        )

    def _build_ssh_command(
        self,
        auth_settings: Dict[str, Optional[str]],
        remote_command: str,
    ) -> List[str]:
        """构建 ssh 命令。"""
        command: List[str] = []
        if auth_settings.get("auth_type") == "password":
            command.extend(["sshpass", "-e"])
        command.extend(
            [
                "ssh",
                *self._common_ssh_options(auth_settings),
                "-p",
                str(self.config.get("port", 22)),
                self._user_at_host(),
                remote_command,
            ]
        )
        return command

    def _build_scp_command(
        self,
        auth_settings: Dict[str, Optional[str]],
        source_path: str,
        target_path: str,
        recursive: bool,
    ) -> List[str]:
        """构建 scp 命令。"""
        command: List[str] = []
        if auth_settings.get("auth_type") == "password":
            command.extend(["sshpass", "-e"])
        command.extend(
            [
                "scp",
                *self._common_ssh_options(auth_settings),
                "-P",
                str(self.config.get("port", 22)),
            ]
        )
        if recursive:
            command.append("-r")
        command.extend([source_path, target_path])
        return command

    def _common_ssh_options(self, auth_settings: Dict[str, Optional[str]]) -> List[str]:
        """构建 ssh/scp 共用选项。"""
        options: List[str] = []
        if auth_settings.get("auth_type") == "password":
            options.extend(
                [
                    "-o",
                    "PreferredAuthentications=password",
                    "-o",
                    "PubkeyAuthentication=no",
                ]
            )
        else:
            options.extend(
                [
                    "-i",
                    auth_settings["key_path"] or "",
                    "-o",
                    "BatchMode=yes",
                ]
            )

        if self.config.get("strict_host_key_checking", True):
            options.extend(["-o", "StrictHostKeyChecking=yes"])
            if auth_settings.get("known_hosts_path"):
                options.extend(
                    ["-o", f"UserKnownHostsFile={auth_settings['known_hosts_path']}"]
                )
        else:
            options.extend(
                [
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                ]
            )

        return options

    def _user_at_host(self) -> str:
        """返回 user@host。"""
        return f"{self.config['username']}@{self.config['host']}"


class TaskExecutor:
    """任务执行器工厂

    根据工具类型选择合适的执行器执行任务。
    """

    EXECUTORS = {
        ToolType.REMOTE_API.value: RemoteAPIExecutor,
        ToolType.DOCKER_IMAGE.value: DockerExecutor,
        ToolType.PYTHON_SCRIPT.value: PythonScriptExecutor,
        ToolType.SSH_JOB.value: SSHJobExecutor,
        "remote_api": RemoteAPIExecutor,
        "docker_image": DockerExecutor,
        "python_script": PythonScriptExecutor,
        "ssh_job": SSHJobExecutor,
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

        Note:
            状态管理由Worker层统一负责,此方法只负责执行逻辑
        """
        executor = self._get_executor()

        try:
            # 执行任务
            result = await executor.execute()
            return result

        except TaskExecutionError:
            # 重新抛出TaskExecutionError,由Worker层处理
            raise

        except Exception as e:
            # 包装其他异常为TaskExecutionError
            logger.exception(f"Task {self.task.id} unexpected error: {e}")
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
