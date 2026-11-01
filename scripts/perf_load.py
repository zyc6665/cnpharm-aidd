#!/usr/bin/env python3
"""离线压测客户端（纯 httpx + asyncio，无需 k6 / locust）。

功能与 ``perf/k6/`` 下的场景对齐，便于在没有 k6 二进制的环境里跑同一批压测，
并输出结构一致的 ``summary.json``。

覆盖场景
--------
* ``smoke``：登录 -> 项目列表 -> 结果列表 -> 任务列表 -> 任务详情（1 个 VU 自检）
* ``read`` ：项目结果列表、产物列表、任务列表（含 cursor 深页）、任务详情
* ``write``：创建项目、提交任务（带 X-Idempotency-Key）、上传小文件
* ``mixed``：按 ``--write-ratio``（默认 0.3）在读写之间随机选择

鉴权
----
Cookie + CSRF：每个 VU 独立 ``httpx.AsyncClient``，登录后浏览器式保存
``cpumodel_access`` / ``cpumodel_csrf`` cookie；写请求（POST/PUT）自动附带
``X-CSRF-Token``（取自 ``cpumodel_csrf`` cookie），与后端 ``_enforce_csrf`` 约定一致。

示例
----
    python scripts/perf_load.py --help
    python scripts/perf_load.py --scenario smoke --vus 1 --iterations 1
    python scripts/perf_load.py --scenario read --vus 10 --duration 60s
    python scripts/perf_load.py --scenario read --vus 50 --duration 120s \\
        --project-id <pid> --deep-pages 20
    python scripts/perf_load.py --scenario mixed --vus 50 --duration 30m \\
        --project-id <pid> --tool-id <tid> --out perf/results/20261101-1200
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
except ImportError:  # pragma: no cover
    print("缺少依赖 httpx，请先 pip install httpx（仓库 requirements.txt 已包含）", file=sys.stderr)
    raise

READ_THRESHOLDS = {"p95_first_page_ms": 300.0, "p95_detail_ms": 150.0}
WRITE_THRESHOLDS = {"p95_task_submit_ms": 800.0, "p95_upload_meta_ms": 1000.0}
ERROR_RATE_LIMIT = 0.005


# --------------------------------------------------------------------------- #
# 参数
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="离线压测（httpx+asyncio），与 perf/k6 场景对齐，输出 summary.json。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1", help="后端 API 根（含 /api/v1）")
    p.add_argument("--username", default="perf_user", help="登录用户名")
    p.add_argument("--password", default="Perf_Passw0rd!", help="登录密码")
    p.add_argument("--project-id", default=None, help="读/写场景使用的已有项目 id（可逗号分隔多个）")
    p.add_argument("--tool-id", default=None, help="提交任务用的 tool_id（write/mixed 需要）")
    p.add_argument("--tool-version-id", default=None, help="提交任务用的 tool_version_id（可空，后端用当前版本）")
    p.add_argument("--scenario", default="smoke", choices=["smoke", "read", "write", "mixed"], help="压测场景")
    p.add_argument("--vus", type=int, default=1, help="并发虚拟用户数")
    p.add_argument("--duration", default="30s", help="持续时间，如 30s / 5m / 30m（--iterations 时忽略）")
    p.add_argument("--iterations", type=int, default=0, help="每个 VU 的迭代次数；>0 时优先于 --duration")
    p.add_argument("--think-time", type=float, default=0.2, help="两次迭代之间平均停顿秒数")
    p.add_argument("--write-ratio", type=float, default=0.3, help="mixed 场景写请求占比")
    p.add_argument("--deep-pages", type=int, default=0, help="read 场景额外翻到的深页页数（0=不深翻）")
    p.add_argument("--page-size", type=int, default=50, help="列表分页大小（<=100）")
    p.add_argument("--out", default=None, help="输出目录（默认 perf/results/<timestamp>）")
    p.add_argument("--seed", type=int, default=42, help="随机种子")
    p.add_argument("--request-timeout", type=float, default=30.0, help="单请求超时秒数")
    return p


def parse_duration(text: str) -> float:
    text = (text or "").strip().lower()
    if not text:
        raise ValueError("duration 为空")
    units = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    for suffix in ("ms", "s", "m", "h"):
        if text.endswith(suffix):
            return float(text[: -len(suffix)]) * units[suffix]
    return float(text)


# --------------------------------------------------------------------------- #
# 统计
# --------------------------------------------------------------------------- #
class Recorder:
    def __init__(self) -> None:
        self.samples: list[float] = []  # ms
        self.status_counts: dict[str, int] = {}
        self.by_endpoint: dict[str, list[float]] = {}
        self.errors: dict[str, int] = {}

    def record(self, endpoint: str, status: int | str, ms: float) -> None:
        self.samples.append(ms)
        key = str(status)
        self.status_counts[key] = self.status_counts.get(key, 0) + 1
        self.by_endpoint.setdefault(endpoint, []).append(ms)

    def record_error(self, endpoint: str, err: str) -> None:
        self.errors[err] = self.errors.get(err, 0) + 1
        self.record(endpoint, "EXC", 0.0)


def percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def summarize(rec: Recorder, elapsed: float) -> dict:
    vals = sorted(rec.samples)
    total = len(vals)
    ok = sum(c for s, c in rec.status_counts.items() if s.startswith("2") or s.startswith("3"))
    server_err = sum(c for s, c in rec.status_counts.items() if s.startswith("5")) + rec.errors.get("__exc__", 0)
    total_exc = sum(v for k, v in rec.errors.items())
    server_err += total_exc
    error_rate = (server_err / total) if total else 0.0
    endpoints = {}
    for ep, arr in rec.by_endpoint.items():
        a = sorted(arr)
        endpoints[ep] = {
            "requests": len(a),
            "p50_ms": round(percentile(a, 50), 2),
            "p95_ms": round(percentile(a, 95), 2),
            "p99_ms": round(percentile(a, 99), 2),
            "max_ms": round(a[-1], 2) if a else 0.0,
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_sec": round(elapsed, 2),
        "requests": total,
        "rps": round(total / elapsed, 2) if elapsed > 0 else 0.0,
        "success": ok,
        "server_errors": server_err,
        "error_rate": round(error_rate, 6),
        "latency_ms": {
            "p50": round(percentile(vals, 50), 2),
            "p90": round(percentile(vals, 90), 2),
            "p95": round(percentile(vals, 95), 2),
            "p99": round(percentile(vals, 99), 2),
            "max": round(vals[-1], 2) if vals else 0.0,
        },
        "status_counts": rec.status_counts,
        "exception_counts": rec.errors,
        "endpoints": endpoints,
    }


# --------------------------------------------------------------------------- #
# 客户端
# --------------------------------------------------------------------------- #
def _pick_items(body: dict) -> tuple[list, str | None]:
    """兼容 paginated_response / 直接 dict 两种信封，返回 (items, next_cursor)。"""
    if not isinstance(body, dict):
        return [], None
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    items = data.get("items") if isinstance(data, dict) else None
    if items is None and isinstance(body.get("items"), list):
        items = body["items"]
    cursor = None
    for src in (data, body):
        if isinstance(src, dict) and src.get("nextCursor"):
            cursor = src["nextCursor"]
            break
    return items or [], cursor


class VU:
    def __init__(self, vu_id: int, args: argparse.Namespace, client: httpx.AsyncClient):
        self.id = vu_id
        self.args = args
        self.client = client
        self.csrf: str | None = None
        self.project_ids: list[str] = [p for p in (args.project_id or "").split(",") if p]
        self.deep_cursor: str | None = None

    async def login(self) -> None:
        r = await self.client.post("/auth/login", json={"username": self.args.username, "password": self.args.password})
        if r.status_code != 200:
            raise RuntimeError(f"VU{self.id} 登录失败 HTTP {r.status_code}: {r.text[:200]}")
        self.csrf = self.client.cookies.get("cpumodel_csrf")

    def _write_headers(self) -> dict:
        h = {}
        if self.csrf:
            h["X-CSRF-Token"] = self.csrf
        return h

    def _project(self) -> str | None:
        if not self.project_ids:
            return None
        return random.choice(self.project_ids)

    # --- 单请求封装 ---
    async def req(self, rec: Recorder, method: str, url: str, *, endpoint: str, **kw) -> httpx.Response | None:
        t0 = time.perf_counter()
        try:
            r = await self.client.request(method, url, **kw)
            ms = (time.perf_counter() - t0) * 1000.0
            rec.record(endpoint, r.status_code, ms)
            return r
        except Exception as exc:  # noqa: BLE001
            ms = (time.perf_counter() - t0) * 1000.0
            rec.record_error(endpoint, type(exc).__name__)
            return None

    # --- 场景动作 ---
    async def warm_deep_cursor(self, rec: Recorder) -> None:
        pid = self._project()
        if not pid or self.args.deep_pages <= 0:
            return
        cursor = None
        for _ in range(self.args.deep_pages):
            params = {"project_id": pid, "page_size": self.args.page_size}
            if cursor:
                params["cursor"] = cursor
            r = await self.req(rec, "GET", "/tasks", endpoint="prep:GET /tasks deep walk", params=params)
            if r is None or r.status_code != 200:
                return
            _, cursor = _pick_items(r.json())
            if not cursor:
                return
        self.deep_cursor = cursor

    async def do_read(self, rec: Recorder) -> None:
        pid = self._project()
        # 1) 结果列表首屏
        await self.req(rec, "GET", f"/projects/{pid}/results", endpoint="GET /projects/{id}/results",
                       params={"page_size": self.args.page_size}) if pid else None
        # 2) 产物列表首屏
        if pid:
            await self.req(rec, "GET", f"/projects/{pid}/artifacts", endpoint="GET /projects/{id}/artifacts",
                           params={"page_size": self.args.page_size})
        # 3) 任务列表首屏
        r = await self.req(rec, "GET", "/tasks", endpoint="GET /tasks",
                           params={"project_id": pid, "page_size": self.args.page_size} if pid else {"page_size": self.args.page_size})
        # 4) 任务详情
        if r is not None and r.status_code == 200:
            items, _ = _pick_items(r.json())
            if items:
                tid = items[0].get("id")
                if tid:
                    await self.req(rec, "GET", f"/tasks/{tid}", endpoint="GET /tasks/{id}")
                    await self.req(rec, "GET", f"/results/{tid}", endpoint="GET /results/{id}")
        # 5) 深页 cursor
        if self.deep_cursor and pid:
            await self.req(rec, "GET", "/tasks", endpoint="GET /tasks (deep cursor)",
                           params={"project_id": pid, "page_size": self.args.page_size, "cursor": self.deep_cursor})

    async def do_write(self, rec: Recorder) -> None:
        # 1) 创建项目
        name = f"perf_load_{self.args.scenario}_{uuid.uuid4().hex[:10]}"
        await self.req(rec, "POST", "/projects", endpoint="POST /projects",
                       json={"name": name, "goal": "perf load"}, headers=self._write_headers())
        # 2) 提交任务（幂等键）
        pid = self._project()
        if self.args.tool_id:
            payload = {"name": f"perf_task_{uuid.uuid4().hex[:8]}", "tool_id": self.args.tool_id, "params": {}}
            if pid:
                payload["project_id"] = pid
            if self.args.tool_version_id:
                payload["tool_version_id"] = self.args.tool_version_id
            await self.req(rec, "POST", "/tasks", endpoint="POST /tasks",
                           json=payload, headers={**self._write_headers(), "X-Idempotency-Key": str(uuid.uuid4())})
        # 3) 小文件上传（元数据/多部分）
        files = {"file": ("perf_small.txt", b"perf load small file\n" * 8, "text/plain")}
        await self.req(rec, "POST", "/files/upload", endpoint="POST /files/upload",
                       files=files, headers=self._write_headers())

    async def run(self, rec: Recorder, stop_at: float) -> None:
        await self.login()
        await self.warm_deep_cursor(rec)
        it = 0
        while True:
            if self.args.iterations > 0:
                if it >= self.args.iterations:
                    break
            elif time.perf_counter() >= stop_at:
                break
            it += 1
            if self.args.scenario == "read":
                await self.do_read(rec)
            elif self.args.scenario == "write":
                await self.do_write(rec)
            elif self.args.scenario == "mixed":
                if random.random() < self.args.write_ratio:
                    await self.do_write(rec)
                else:
                    await self.do_read(rec)
            else:  # smoke：读路径各来一次
                await self.do_read(rec)
            if self.args.think_time > 0:
                await asyncio.sleep(random.uniform(0, self.args.think_time * 2))


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
async def run(args: argparse.Namespace) -> dict:
    duration = parse_duration(args.duration)
    rec = Recorder()
    timeout = httpx.Timeout(args.request_timeout)
    limits = httpx.Limits(max_connections=max(50, args.vus * 2), max_keepalive_connections=max(20, args.vus))
    clients = [
        httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=timeout, limits=limits, follow_redirects=True)
        for _ in range(args.vus)
    ]
    vus = [VU(i, args, clients[i]) for i in range(args.vus)]
    stop_at = time.perf_counter() + duration if args.iterations <= 0 else 0.0

    t0 = time.perf_counter()
    results = await asyncio.gather(*(v.run(rec, stop_at) for v in vus), return_exceptions=True)
    elapsed = time.perf_counter() - t0

    for i, res in enumerate(results):
        if isinstance(res, Exception):
            print(f"[VU{i}] 异常终止: {type(res).__name__}: {res}", file=sys.stderr)

    for c in clients:
        await c.aclose()

    summary = summarize(rec, elapsed)
    summary["scenario"] = args.scenario
    summary["vus"] = args.vus
    summary["base_url"] = args.base_url
    summary["config"] = {
        "duration": args.duration,
        "iterations": args.iterations,
        "deep_pages": args.deep_pages,
        "page_size": args.page_size,
        "write_ratio": args.write_ratio,
    }

    # SLO 判定
    ep = summary["endpoints"]
    slo: dict = {"error_rate": summary["error_rate"], "error_rate_limit": ERROR_RATE_LIMIT}
    failures = []
    if summary["error_rate"] > ERROR_RATE_LIMIT:
        failures.append(f"错误率 {summary['error_rate']:.4f} > {ERROR_RATE_LIMIT}")
    for key in ("GET /projects/{id}/results", "GET /tasks", "GET /projects/{id}/artifacts"):
        if key in ep and ep[key]["p95_ms"] > READ_THRESHOLDS["p95_first_page_ms"]:
            failures.append(f"{key} P95 {ep[key]['p95_ms']}ms > {READ_THRESHOLDS['p95_first_page_ms']}ms")
    if "GET /tasks/{id}" in ep and ep["GET /tasks/{id}"]["p95_ms"] > READ_THRESHOLDS["p95_detail_ms"]:
        failures.append(f"GET /tasks/{{id}} P95 {ep['GET /tasks/{id}']['p95_ms']}ms > {READ_THRESHOLDS['p95_detail_ms']}ms")
    if "POST /tasks" in ep and ep["POST /tasks"]["p95_ms"] > WRITE_THRESHOLDS["p95_task_submit_ms"]:
        failures.append(f"POST /tasks P95 {ep['POST /tasks']['p95_ms']}ms > {WRITE_THRESHOLDS['p95_task_submit_ms']}ms")
    if "POST /files/upload" in ep and ep["POST /files/upload"]["p95_ms"] > WRITE_THRESHOLDS["p95_upload_meta_ms"]:
        failures.append(f"POST /files/upload P95 {ep['POST /files/upload']['p95_ms']}ms > {WRITE_THRESHOLDS['p95_upload_meta_ms']}ms")
    slo["passed"] = not failures
    slo["failures"] = failures
    summary["slo"] = slo
    return summary


def print_summary(s: dict) -> None:
    print("\n===== perf_load summary =====")
    print(f"scenario : {s['scenario']}  vus={s['vus']}  duration={s['duration_sec']}s")
    print(f"requests : {s['requests']}  rps={s['rps']}")
    print(f"latency  : p50={s['latency_ms']['p50']}ms p95={s['latency_ms']['p95']}ms p99={s['latency_ms']['p99']}ms")
    print(f"error    : {s['error_rate']:.4%}  status={s['status_counts']}")
    print("endpoints:")
    for ep, v in sorted(s["endpoints"].items()):
        print(f"  {ep:38s} n={v['requests']:<5d} p95={v['p95_ms']:<8.1f} p99={v['p99_ms']:<8.1f} max={v['max_ms']:.1f}")
    print(f"SLO      : {'PASS' if s['slo']['passed'] else 'FAIL'} {s['slo']['failures']}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.vus <= 0:
        print("--vus 必须 > 0", file=sys.stderr)
        return 2
    random.seed(args.seed)
    summary = asyncio.run(run(args))

    out_dir = Path(args.out) if args.out else (Path(__file__).resolve().parents[1] / "perf" / "results" /
                                              datetime.now().strftime("%Y%m%d-%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "summary.json"
    out_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print_summary(summary)
    print(f"\nsummary.json -> {out_file}")
    return 0 if summary["slo"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
