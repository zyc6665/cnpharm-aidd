"""SSH 作业结果文件读取。"""

import json
from pathlib import Path
from typing import Any

from app.tasks.executors.errors import TaskExecutionError


def load_result_json(download_root: str | None) -> dict[str, Any]:
    if not download_root:
        raise TaskExecutionError("Missing downloaded output directory for ssh_job")
    result_path = Path(download_root) / "output" / "result.json"
    if not result_path.exists():
        raise TaskExecutionError("Missing output/result.json from ssh_job", details={"download_root": download_root})
    try:
        with result_path.open("r", encoding="utf-8") as result_file:
            return json.load(result_file)
    except json.JSONDecodeError as exc:
        raise TaskExecutionError(f"Invalid output/result.json from ssh_job: {exc}", details={"result_path": str(result_path)}) from exc
