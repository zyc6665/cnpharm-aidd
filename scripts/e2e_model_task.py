#!/usr/bin/env python3
"""模型接入 E2E：上传输入文件 → 创建任务 → 轮询到终态 → 打印产出。

用法（在 backend/ 目录、平台后端已启动时）：
    python ../scripts/e2e_model_task.py --tool <tool_id> --version <version_id> \
        --file protein_pdb=./protein.pdb --file ligand_pdb=./ligand.pdb \
        --params '{"distance": 5.0, "device": "cpu"}'

--file 的 key 必须与工具 input_schema 中 format=file 的字段名一致。
登录账号默认读 backend/.tmp_mw.env 的 ADMIN_EMAIL/ADMIN_PASSWORD，也可用
环境变量 E2E_USERNAME / E2E_PASSWORD 覆盖。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import requests

BASE = "http://127.0.0.1:8000/api/v1"


def _load_credentials() -> tuple[str, str]:
    env_path = pathlib.Path("backend/.tmp_mw.env")
    if not env_path.exists():
        env_path = pathlib.Path(".tmp_mw.env")
    values: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    username = values.get("E2E_USERNAME") or values.get("ADMIN_EMAIL", "").split("@")[0]
    password = values.get("E2E_PASSWORD") or values.get("ADMIN_PASSWORD", "")
    return username, password


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--file", action="append", default=[], metavar="FIELD=PATH")
    parser.add_argument("--params", default="{}")
    parser.add_argument("--name", default="模型接入 E2E")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    file_fields: dict[str, pathlib.Path] = {}
    for item in args.file:
        field, _, path = item.partition("=")
        if not field or not path:
            parser.error(f"--file 需要 FIELD=PATH，收到 {item!r}")
        file_fields[field] = pathlib.Path(path)

    username, password = _load_credentials()
    session = requests.Session()
    response = session.post(f"{BASE}/auth/login", json={"username": username, "password": password})
    response.raise_for_status()
    csrf = session.cookies.get("cpumodel_csrf")
    if csrf:
        session.headers["X-CSRF-Token"] = csrf

    file_ids: dict[str, str] = {}
    for field, path in file_fields.items():
        with open(path, "rb") as handle:
            response = session.post(f"{BASE}/files/upload", files={"file": (path.name, handle)})
        response.raise_for_status()
        file_ids[field] = response.json()["data"]["id"]
        print(f"UPLOAD {field} {path.name} -> {file_ids[field]}")

    payload = {
        "name": args.name,
        "tool_id": args.tool,
        "tool_version_id": args.version,
        "params": {"params": json.loads(args.params), "input_files": file_ids},
        "file_ids": list(file_ids.values()),
    }
    response = session.post(f"{BASE}/tasks", json=payload)
    response.raise_for_status()
    task_id = response.json()["data"]["id"]
    print(f"TASK {task_id}")

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        time.sleep(5)
        try:
            data = session.get(f"{BASE}/tasks/{task_id}", timeout=30).json().get("data", {})
        except Exception as exc:  # noqa: BLE001 - 轮询允许瞬时断连
            print(f"POLL transient: {exc}")
            continue
        print(f"POLL {data.get('status')} {data.get('progress')} {data.get('progress_message') or ''}")
        if data.get("status") in {"success", "completed", "failed", "cancelled", "timeout"}:
            print("OUTPUTS", json.dumps(data.get("outputs"), ensure_ascii=False)[:2000])
            print("OUTFILES", json.dumps(data.get("output_files"), ensure_ascii=False)[:1000])
            print("ERROR", data.get("error_message"))
            return 0 if data.get("status") in {"success", "completed"} else 1
    print("TIMEOUT waiting for task")
    return 1


if __name__ == "__main__":
    sys.exit(main())
