#!/usr/bin/env python3
"""Run AT-003 MolP-PC smoke through platform APIs and collect evidence."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from collect_at003_platform_evidence import collect_record  # noqa: E402


DEFAULT_TASK_GROUPS = ["Absorption"]


def _unwrap_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _api_request(
    method: str,
    base_url: str,
    path: str,
    *,
    token: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Platform API {method} {path} failed: HTTP {exc.code}: {body}") from exc


def _task_payload(
    *,
    project_id: str,
    tool_id: str,
    input_artifact_version_id: str,
    task_groups: list[str],
    name: str | None,
    tool_version_id: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name or "AT-003 MolP-PC platform API smoke",
        "project_id": project_id,
        "tool_id": tool_id,
        "params": {"task_groups": task_groups},
        "input_bindings": {"molecules": input_artifact_version_id},
        "priority": "normal",
    }
    if tool_version_id:
        payload["tool_version_id"] = tool_version_id
    return payload


def _terminal_status(status: str) -> bool:
    return status in {"success", "failed", "failure", "error", "canceled", "cancelled"}


def run_smoke(
    *,
    base_url: str,
    token: str,
    project_id: str,
    tool_id: str,
    input_artifact_version_id: str,
    tool_version_id: str | None = None,
    task_groups: list[str] | None = None,
    name: str | None = None,
    output_path: Path | None = None,
    poll_interval_sec: float = 3.0,
    timeout_sec: float = 900.0,
) -> dict[str, Any]:
    payload = _task_payload(
        project_id=project_id,
        tool_id=tool_id,
        input_artifact_version_id=input_artifact_version_id,
        task_groups=task_groups or DEFAULT_TASK_GROUPS,
        name=name,
        tool_version_id=tool_version_id,
    )

    preview = _unwrap_data(
        _api_request("POST", base_url, "/api/v1/tasks/prepare-preview", token=token, payload=payload)
    )
    if not isinstance(preview, dict) or preview.get("ready") is not True:
        reason = preview.get("blocked_reason") if isinstance(preview, dict) else None
        raise ValueError(f"AT-003 smoke preview is not ready: {reason or 'unknown reason'}")

    created = _unwrap_data(
        _api_request("POST", base_url, "/api/v1/tasks", token=token, payload=payload, timeout=60)
    )
    task_id = str(created.get("id") or "") if isinstance(created, dict) else ""
    if not task_id:
        raise RuntimeError("Platform task creation response did not include task id")

    deadline = time.monotonic() + timeout_sec
    detail: dict[str, Any] = {}
    while True:
        raw_detail = _unwrap_data(
            _api_request("GET", base_url, f"/api/v1/tasks/{task_id}", token=token)
        )
        detail = raw_detail if isinstance(raw_detail, dict) else {}
        status = str(detail.get("status") or "").lower()
        if _terminal_status(status):
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(f"AT-003 smoke task timed out: {task_id}")
        time.sleep(max(0.0, poll_interval_sec))

    if str(detail.get("status") or "").lower() != "success":
        message = detail.get("error_message") or detail.get("progress_message") or "unknown error"
        raise RuntimeError(f"AT-003 smoke task failed: {task_id}: {message}")

    record = collect_record(base_url, token, task_id)
    if output_path is not None:
        output_path.write_text(record.rstrip() + "\n", encoding="utf-8")

    return {
        "task_id": task_id,
        "status": detail.get("status"),
        "project_id": detail.get("project_id"),
        "tool_slug": detail.get("tool_slug"),
        "tool_version_id": detail.get("tool_version_id"),
        "output": str(output_path) if output_path is not None else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AT-003 MolP-PC platform smoke.")
    parser.add_argument("--base-url", required=True, help="Platform base URL")
    parser.add_argument("--token", required=True, help="Bearer token for the platform API")
    parser.add_argument("--project-id", required=True, help="Project id for the task")
    parser.add_argument("--tool-id", required=True, help="MolP-PC platform tool id")
    parser.add_argument("--tool-version-id", help="Optional explicit ToolVersion id")
    parser.add_argument("--input-artifact-version-id", required=True, help="molecule_table@1 input ArtifactVersion id")
    parser.add_argument("--task-group", action="append", dest="task_groups", help="MolP-PC task group, repeatable")
    parser.add_argument("--name", help="Optional task name")
    parser.add_argument("--output", help="Optional Markdown evidence output path")
    parser.add_argument("--poll-interval-sec", type=float, default=3.0)
    parser.add_argument("--timeout-sec", type=float, default=900.0)
    args = parser.parse_args(argv)

    result = run_smoke(
        base_url=args.base_url,
        token=args.token,
        project_id=args.project_id,
        tool_id=args.tool_id,
        tool_version_id=args.tool_version_id,
        input_artifact_version_id=args.input_artifact_version_id,
        task_groups=args.task_groups,
        name=args.name,
        output_path=Path(args.output) if args.output else None,
        poll_interval_sec=args.poll_interval_sec,
        timeout_sec=args.timeout_sec,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
