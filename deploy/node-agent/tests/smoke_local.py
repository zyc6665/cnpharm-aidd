"""本地冒烟测试：验证 drp-node-agent 的卡位/作业生命周期与状态上报。

不依赖 GPU：用一个可立即退出的小镜像（默认 python:3.10-slim）跑一条作业，
断言：健康检查、卡位列表、提交→SUCCEEDED、卡位最终回到 FREE、平台收到上报。

运行：在 deploy/node-agent 目录
    python tests/smoke_local.py
可用 SMOKE_IMAGE 指定本地已有镜像（需能执行 `python -c`）。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SLOTS = Path(__file__).resolve().parent / "local.slots.yaml"
WORK = Path(os.environ.get("TEMP", "/tmp")) / "drp-agent-smoke-work"
REPORTS = []
PORT = 8799

os.environ.update(
    {
        "DRP_SLOTS_FILE": str(SLOTS),
        "DRP_WORK_ROOT": str(WORK),
        "DRP_AGENT_HOST": "127.0.0.1",
        "DRP_AGENT_PORT": "8780",
        "DRP_AGENT_API_TOKEN": "test-agent-token",
        "DRP_AGENT_REPORT_TOKEN": "test-report-token",
        "DRP_PLATFORM_BASE_URL": "http://127.0.0.1:%d/api/v1" % PORT,
        "DRP_REPORT_INTERVAL_SECONDS": "2",
    }
)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body)
        except Exception:  # noqa: BLE001
            data = {"raw": body.decode("utf-8", "replace")}
        REPORTS.append({"path": self.path, "token": self.headers.get("X-DRP-Agent-Token"), "data": data})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *args):  # silence
        return


def wait_terminal(client, auth, job_id, timeout=90):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        resp = client.get("/api/v1/jobs/%s" % job_id, headers=auth)
        last = resp.json()
        if last.get("state") in ("SUCCEEDED", "FAILED", "CANCELED", "TIMEOUT", "FAULT"):
            return last
        time.sleep(1)
    return last


def main() -> int:
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    from fastapi.testclient import TestClient
    import drp_node_agent.server as agent_server

    image = os.environ.get("SMOKE_IMAGE", "python:3.10-slim")
    auth = {"Authorization": "Bearer test-agent-token"}
    with TestClient(agent_server.app) as client:
        health = client.get("/healthz").json()
        print("healthz:", health)
        slots = client.get("/api/v1/slots", headers=auth).json()
        print("slots:", slots)
        assert health["status"] == "ok" and health["slots"] == 1

        submit = client.post(
            "/api/v1/jobs",
            headers=auth,
            json={
                "taskId": "task-smoke-1",
                "slotId": "A0",
                "image": image,
                "modelEntry": ["python3", "-c", "print('drp-agent-smoke-ok')"],
                "maxMinutes": 1,
            },
        )
        print("submit:", submit.status_code, submit.text)
        assert submit.status_code == 200, submit.text
        job_id = submit.json()["jobId"]

        status = wait_terminal(client, auth, job_id)
        print("terminal status:", status)
        assert status.get("state") == "SUCCEEDED", status
        assert status.get("exitCode") == 0, status

        final_slots = client.get("/api/v1/slots", headers=auth).json()
        print("final slots:", final_slots)
        assert final_slots[0]["state"] == "FREE", final_slots

        time.sleep(3)  # 等一轮上报
    server.shutdown()

    print("reports received:", len(REPORTS))
    print("sample report:", REPORTS[:2])
    assert REPORTS, "平台未收到卡位状态上报"
    assert any(r["data"].get("slotId") == "A0" for r in REPORTS), REPORTS[:3]
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
