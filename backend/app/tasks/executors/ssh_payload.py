"""SSH 作业参数载荷构建。"""

from typing import Any


def build_params_payload(task_id: str, raw_params: Any, staged_files: list[dict[str, str]]) -> dict[str, Any]:
    raw_params = raw_params or {}
    if isinstance(raw_params, dict) and ("params" in raw_params or "input_files" in raw_params):
        payload = {"task_id": task_id, "params": raw_params.get("params", {}), "input_files": raw_params.get("input_files", {})}
        payload.update({key: value for key, value in raw_params.items() if key not in {"params", "input_files"}})
    else:
        payload = {"task_id": task_id, "params": raw_params if isinstance(raw_params, dict) else {}, "input_files": {}}
    if staged_files:
        payload["uploaded_files"] = [{"file_id": item["file_id"], "filename": item["filename"], "path": item["relative_path"]} for item in staged_files]
        payload["files"] = [item["relative_path"] for item in staged_files]
    return payload
