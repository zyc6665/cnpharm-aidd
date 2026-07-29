"""Python 脚本执行结果解析。"""

import json
from pathlib import Path
from typing import Any


def parse_script_output(work_dir: str, stdout: str) -> dict[str, Any]:
    result_path = Path(work_dir) / "output" / "result.json"
    if result_path.exists():
        with result_path.open("r", encoding="utf-8") as result_file:
            return json.load(result_file)
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"raw_output": stdout}
