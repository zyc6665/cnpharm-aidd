"""Python 脚本执行器。"""

import asyncio
import json
import logging
import os
import subprocess
from typing import Any

from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.errors import TaskExecutionError
from app.tasks.executors.script_output import parse_script_output
from app.tasks.executors.script_trust import validate_script_trust

logger = logging.getLogger(__name__)


def _configured_args(config: dict[str, Any]) -> list[str]:
    args = config.get("args", [])
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise TaskExecutionError("Python script args must be a string array")
    return args


class PythonScriptExecutor(BaseExecutor):
    """执行经过可信校验的 Python 工具脚本。"""

    async def execute(self) -> dict[str, Any]:
        script_path = self.config.get("script_path")
        script_content = self.config.get("script_content")
        timeout = self.config.get("timeout_sec", 600)
        if not script_path and not script_content:
            raise TaskExecutionError("Missing script_path or script_content in tool config")
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
                env={**os.environ, "PYTHONPATH": work_dir},
            )
            if process.returncode != 0:
                raise TaskExecutionError(
                    f"Python script failed with code {process.returncode}",
                    details={"stderr": (process.stderr or "")[:1000]},
                )
            output = parse_script_output(work_dir, process.stdout)
            output_files = await self._collect_output_files()
            if output_files:
                output["output_file_ids"] = output_files
            return {"success": True, "result": output, "stdout": process.stdout, "stderr": process.stderr}
        except subprocess.TimeoutExpired as exc:
            raise TaskExecutionError("Python script execution timeout") from exc
        except TaskExecutionError:
            raise
        except Exception as exc:
            raise TaskExecutionError(f"Python script execution error: {exc}") from exc
        finally:
            self._cleanup_work_dir()

    def _validate_script_trust(self, script_content: str | None, script_path: str | None) -> None:
        validate_script_trust(script_content, script_path)

    async def _collect_output_files(self) -> list[str]:
        output_dir = os.path.join(self._get_work_dir(), "output")
        if not os.path.exists(output_dir):
            return []
        return await super()._collect_output_files(
            [os.path.join(output_dir, filename) for filename in os.listdir(output_dir)],
            skip_names={"result.json"},
        )
