"""SSH 作业结果文件读取。"""

import json
from pathlib import Path
from typing import Any

from app.tasks.executors.errors import TaskExecutionError


def load_result_json(download_root: str | None) -> dict[str, Any]:
    if not download_root:
        raise TaskExecutionError("ssh_job 缺少已下载的输出目录")
    result_path = Path(download_root) / "output" / "result.json"
    if not result_path.exists():
        raise TaskExecutionError("ssh_job 缺少 output/result.json", details={"download_root": download_root})
    try:
        with result_path.open("r", encoding="utf-8") as result_file:
            return json.load(result_file)
    except json.JSONDecodeError as exc:
        raise TaskExecutionError(f"ssh_job 的 output/result.json 格式无效：{exc}", details={"result_path": str(result_path)}) from exc
