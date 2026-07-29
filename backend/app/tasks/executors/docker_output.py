"""Docker 工具标准输出解析。"""

import json
from typing import Any


def parse_docker_output(stdout: str) -> dict[str, Any]:
    """优先解析标记 JSON，其次解析最后一行 JSON。"""
    try:
        if "OUTPUT_JSON:" in stdout:
            json_start = stdout.index("OUTPUT_JSON:") + len("OUTPUT_JSON:")
            return json.loads(stdout[json_start:].strip().split("\n")[0])

        for line in reversed(stdout.strip().split("\n")):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        return {"raw_output": stdout}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"raw_output": stdout}
