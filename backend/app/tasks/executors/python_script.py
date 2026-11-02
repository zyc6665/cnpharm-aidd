"""Python 脚本执行器。"""

import asyncio
import json
import logging
import os
import subprocess
from typing import Any

from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.errors import TaskExecutionError, TaskTimeoutError
from app.tasks.executors.script_output import parse_script_output
from app.tasks.executors.script_trust import validate_script_trust

logger = logging.getLogger(__name__)

# 脚本运行在平台主机进程内，若原样继承 os.environ 会把数据库口令、缓存/对象存储
# 密钥、JWT/加密密钥等平台机密暴露给工具脚本。这里按名称黑名单剥离敏感变量，
# 只保留运行所需的通用环境（PATH/HOME/临时目录等）。
_SENSITIVE_ENV_MARKERS = (
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "TOKEN",
    "API_KEY",
    "PRIVATE_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "MINIO",
    "AWS_",
    "JWT",
    "ENCRYPTION_KEY",
)


def _build_script_env(work_dir: str) -> dict[str, str]:
    """构造工具脚本的运行环境，剥离平台敏感变量并注入 PYTHONPATH。"""
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in _SENSITIVE_ENV_MARKERS)
    }
    env["PYTHONPATH"] = work_dir
    return env



def _configured_args(config: dict[str, Any]) -> list[str]:
    args = config.get("args", [])
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise TaskExecutionError("Python 脚本参数必须是字符串数组")
    return args


class PythonScriptExecutor(BaseExecutor):
    """执行经过可信校验的 Python 工具脚本。"""

    async def execute(self) -> dict[str, Any]:
        script_path = self.config.get("script_path")
        script_content = self.config.get("script_content")
        timeout = self.config.get("timeout_sec", 600)
        if not script_path and not script_content:
            raise TaskExecutionError("工具配置缺少 script_path 或 script_content")
        validate_script_trust(script_content, script_path)
        configured_args = _configured_args(self.config)
        work_dir = self._get_work_dir()
        try:
            if script_content:
                script_path = os.path.join(work_dir, "script.py")
                with open(script_path, "w", encoding="utf-8") as script_file:
                    script_file.write(script_content)
            params_file = os.path.join(work_dir, "params.json")
            with open(params_file, "w", encoding="utf-8") as params_handle:
                json.dump(self.task.inputs.params if self.task.inputs else {}, params_handle)
            process = await asyncio.to_thread(
                subprocess.run,
                [
                    "python",
                    script_path,
                    *configured_args,
                    "--params-file",
                    params_file,
                    "--output-dir",
                    os.path.join(work_dir, "output"),
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=work_dir,
                env=_build_script_env(work_dir),
            )
            if process.returncode != 0:
                raise TaskExecutionError(
                    f"Python 脚本执行失败，退出码 {process.returncode}",
                    details={"stderr": (process.stderr or "")[:1000]},
                )
            output = parse_script_output(work_dir, process.stdout)
            output_files = await self._collect_output_files()
            if output_files:
                output["output_file_ids"] = output_files
            return {"success": True, "result": output, "stdout": process.stdout, "stderr": process.stderr}
        except subprocess.TimeoutExpired as exc:
            raise TaskTimeoutError(
                f"Python 脚本执行超时（{timeout} 秒）",
                timeout_sec=timeout,
            ) from exc
        except TaskExecutionError:
            raise
        except Exception as exc:
            raise TaskExecutionError(f"Python 脚本执行异常：{exc}") from exc
        finally:
            self._cleanup_work_dir()

    def _validate_script_trust(self, script_content: str | None, script_path: str | None) -> None:
        validate_script_trust(script_content, script_path)

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
