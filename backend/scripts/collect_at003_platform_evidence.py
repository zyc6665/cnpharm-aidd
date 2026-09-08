#!/usr/bin/env python3
"""Collect AT-003 MolP-PC platform smoke evidence from platform APIs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


EXPECTED_TOOL_SLUG = "molp-pc-property-prediction"


def _unwrap_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _api_get(base_url: str, path: str, *, token: str, params: dict[str, str] | None = None) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{base_url.rstrip('/')}{path}{query}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - operator supplied platform URL
        return json.loads(response.read().decode("utf-8"))


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _join_mapping(value: Any) -> str:
    mapping = _as_dict(value)
    if not mapping:
        return "N/A"
    return ", ".join(f"{key} -> {val}" for key, val in sorted(mapping.items()))


def _file_hashes(files: Any) -> str:
    parts: list[str] = []
    for item in _as_list(files):
        file_data = _as_dict(item)
        sha256 = str(file_data.get("sha256") or "").strip()
        if not sha256:
            continue
        filename = str(file_data.get("filename") or file_data.get("original_name") or "file")
        parts.append(f"{filename}: {sha256}")
    return "; ".join(parts) if parts else "N/A"


def _tool_version(task: dict[str, Any]) -> str:
    tool = _as_dict(task.get("tool"))
    current_version = _as_dict(tool.get("current_version"))
    return str(current_version.get("version") or task.get("tool_version") or "N/A")


def _artifact_metadata(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    for artifact in artifacts:
        version = _as_dict(artifact.get("latest_version"))
        manifest = _as_dict(version.get("manifest_json"))
        metadata = _as_dict(manifest.get("metadata"))
        if metadata:
            return metadata
    return {}


def _artifact_rows(artifacts: list[dict[str, Any]]) -> str:
    rows = ["| 输出 | 标准类型 | ArtifactVersion | artifact_version_id | 文件 role / checksum |", "| --- | --- | --- | --- | --- |"]
    for artifact in artifacts:
        version = _as_dict(artifact.get("latest_version"))
        files = []
        for file_item in _as_list(version.get("files")):
            file_data = _as_dict(file_item)
            role = str(file_data.get("role") or "file")
            checksum = str(file_data.get("sha256") or "N/A")
            files.append(f"{role}: {checksum}")
        rows.append(
            "| {name} | {standard_type} | {artifact_version} | {artifact_version_id} | {files} |".format(
                name=artifact.get("name") or "N/A",
                standard_type=artifact.get("standard_type") or "N/A",
                artifact_version=version.get("version") or "latest",
                artifact_version_id=version.get("id") or artifact.get("latest_version_id") or "N/A",
                files="; ".join(files) if files else "N/A",
            )
        )
    return "\n".join(rows)


def _metadata_row(metadata: dict[str, Any], key: str, expected: str) -> str:
    return f"| {key} | {expected} | {metadata.get(key) or 'N/A'} |"


def build_record_markdown(task: dict[str, Any], artifacts: list[dict[str, Any]]) -> str:
    """Render the AT-003 platform evidence record from API payloads."""
    tool_slug = str(task.get("tool_slug") or "")
    if tool_slug != EXPECTED_TOOL_SLUG:
        raise ValueError(f"AT-003 平台验收任务必须是 {EXPECTED_TOOL_SLUG}，实际为 {tool_slug or 'N/A'}")

    dispatch = _as_dict(task.get("dispatch"))
    metadata = _artifact_metadata(artifacts)
    return "\n".join(
        [
            "# AT-003 平台工具调用真实运行记录",
            "",
            "> 本记录来自平台 API。不得记录 `model/MolP-PC/platform_run.sh` 作为 AT-003 平台验收结果。",
            "",
            "## 1. 平台任务记录",
            "",
            "| 字段 | 记录值 |",
            "| --- | --- |",
            f"| 项目 ID | {task.get('project_id') or 'N/A'} |",
            f"| 工具 slug | {tool_slug} |",
            f"| ToolVersion | {_tool_version(task)} |",
            f"| tool_version_id | {task.get('tool_version_id') or 'N/A'} |",
            f"| task_id | {task.get('id') or 'N/A'} |",
            f"| 调度模式 | {dispatch.get('mode') or 'N/A'} |",
            f"| 调度队列 | {dispatch.get('queue') or 'N/A'} |",
            f"| 标准输入绑定 | {_join_mapping(task.get('input_bindings'))} |",
            f"| 任务状态 | {task.get('status') or 'N/A'} |",
            "",
            "## 2. 输入与输出哈希",
            "",
            "| 字段 | 记录值 |",
            "| --- | --- |",
            f"| input_sha256 | {_file_hashes(task.get('input_files'))} |",
            f"| output_sha256 | {_file_hashes(task.get('output_files'))} |",
            "",
            "## 3. 输出 Artifact 记录",
            "",
            _artifact_rows(artifacts),
            "",
            "## 4. 科学元数据核对",
            "",
            "| 字段 | 预期 | 实际 |",
            "| --- | --- | --- |",
            _metadata_row(metadata, "model_name", "MolP-PC"),
            _metadata_row(metadata, "model_version", "0.1.1"),
            _metadata_row(metadata, "endpoint_ref", "与 Tool Package 声明一致"),
            _metadata_row(metadata, "runtime_ref", "与 Tool Package 声明一致"),
            _metadata_row(metadata, "weights_ref", "与 Tool Package 声明一致"),
            _metadata_row(metadata, "evidence_level", "engineering_smoke_only"),
            _metadata_row(metadata, "applicability_domain_status", "unknown 或模型实际输出"),
            "",
            "## 5. 结论",
            "",
            "| 字段 | 记录值 |",
            "| --- | --- |",
            "| 验收结论 | 待人工确认 |",
            "| 阻断问题 | 如无则填 N/A |",
        ]
    )


def task_id_from_workflow_run(run: dict[str, Any], workflow_node_id: str) -> str:
    """Return the platform task id bound to a workflow node state."""
    node_states = _as_dict(run.get("node_states"))
    node_state = _as_dict(node_states.get(workflow_node_id))
    task_id = str(node_state.get("task_id") or "").strip()
    if not task_id:
        raise ValueError(
            f"workflow node {workflow_node_id} in run {run.get('id') or 'N/A'} 缺少 task_id"
        )
    return task_id


def collect_record(base_url: str, token: str, task_id: str) -> str:
    task = _unwrap_data(_api_get(base_url, f"/api/v1/tasks/{task_id}", token=token))
    task_data = _as_dict(task)
    project_id = str(task_data.get("project_id") or "")
    if not project_id:
        raise ValueError("任务详情缺少 project_id，无法查询平台 Artifact 证据")

    artifact_payload = _unwrap_data(
        _api_get(
            base_url,
            f"/api/v1/projects/{project_id}/artifacts",
            token=token,
            params={"source_task_id": task_id},
        )
    )
    artifacts = [_as_dict(item) for item in _as_list(_as_dict(artifact_payload).get("items"))]
    return build_record_markdown(task_data, artifacts)


def collect_record_from_workflow_node(
    base_url: str,
    token: str,
    *,
    workflow_run_id: str,
    workflow_node_id: str,
) -> str:
    run = _unwrap_data(
        _api_get(base_url, f"/api/v1/workflows/runs/{workflow_run_id}", token=token)
    )
    task_id = task_id_from_workflow_run(_as_dict(run), workflow_node_id)
    return collect_record(base_url, token, task_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect AT-003 MolP-PC platform smoke evidence.")
    parser.add_argument("--base-url", required=True, help="Platform base URL, for example http://127.0.0.1:8000")
    parser.add_argument("--token", required=True, help="Bearer token for the platform API")
    parser.add_argument("--task-id", help="MolP-PC platform task id")
    parser.add_argument("--workflow-run-id", help="WorkflowRun id that contains the MolP-PC node")
    parser.add_argument("--workflow-node-id", help="Workflow node id for the MolP-PC task")
    parser.add_argument("--output", help="Optional markdown output path")
    args = parser.parse_args(argv)

    if args.task_id:
        record = collect_record(args.base_url, args.token, args.task_id)
    elif args.workflow_run_id and args.workflow_node_id:
        record = collect_record_from_workflow_node(
            args.base_url,
            args.token,
            workflow_run_id=args.workflow_run_id,
            workflow_node_id=args.workflow_node_id,
        )
    else:
        parser.error("需要提供 --task-id，或同时提供 --workflow-run-id 与 --workflow-node-id")

    if args.output:
        Path(args.output).write_text(record + "\n", encoding="utf-8")
    else:
        print(record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
