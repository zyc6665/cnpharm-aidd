# perf/ — 阶段 4 压测准备

本目录是「阶段 4：压测准备」的可执行压测资产，**只做压测准备与自检**，不跑长时间压测。
覆盖：登录（Cookie + CSRF）、项目/结果/产物/任务列表（含 cursor 深页）、任务详情、
创建项目、提交任务（幂等键）、小文件上传。两套等价实现：

* `perf/k6/` —— k6 官方单文件脚本（首选，指标最全）；
* `scripts/perf_load.py` —— 纯 `httpx + asyncio` 离线实现（无 k6 时也能跑，输出 `summary.json`）。

---

## 1. 目录结构

```
perf/
├── README.md                # 本文件
├── collect.sh               # 压测前后 EXPLAIN + /metrics 快照
├── .gitignore               # 忽略 bin/ 与 results/
├── k6/
│   ├── smoke.js             # 1 VU 单轮连通自检
│   ├── read.js              # 读场景阶梯 10→50→100 VU，含深页 cursor
│   ├── write.js             # 写场景：创建项目 / 提交任务 / 上传小文件
│   ├── mixed.js             # 70% 读 + 30% 写 soak（默认 30min）
│   └── lib/
│       ├── auth.js          # 登录 + Cookie/CSRF
│       ├── data.js          # 配置与响应解析
│       └── thresholds.js    # 按 SLO 的 k6 阈值
└── bin/                     # 放 k6(.exe)，已 gitignore（不提交）
```

相关脚本（仓库根）：

* `scripts/perf_seed.py` —— 压测造数（幂等、参数化，默认 20 项目 × 5000 任务 = 10 万任务、20 万产物）。
* `scripts/perf_load.py` —— 离线压测客户端（httpx + asyncio）。

---

## 2. 前置

* 后端已启动并可访问（如 `http://127.0.0.1:8000`）。
* 数据库可写（造数直连 `DATABASE_URL`，默认 PostgreSQL）。
* Python 依赖：`httpx`、`sqlalchemy`、`asyncpg`（均已在 `backend/requirements.txt`）。
* k6（可选）：从 <https://github.com/grafana/k6/releases> 下载单文件，放到 `perf/bin/k6`
  （Windows 为 `perf/bin/k6.exe`），或系统 PATH 里已有 `k6`。

---

## 3. 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PERF_BASE_URL` | `http://127.0.0.1:8000/api/v1` | 后端 API 根（含 `/api/v1`） |
| `PERF_USERNAME` | `perf_user` | 登录用户名 |
| `PERF_PASSWORD` | 造数脚本打印的密码 | 登录密码 |
| `PERF_PROJECT_ID` | 造数脚本打印 | 读/写场景使用的项目 id（可逗号分隔多个） |
| `PERF_TOOL_ID` | 造数脚本打印 | 写场景提交任务用的 tool_id |
| `PERF_TOOL_VERSION_ID` | 造数脚本打印 | 提交任务的 tool_version_id（可空） |
| `PERF_PAGE_SIZE` | `50` | 列表分页大小（≤100） |
| `PERF_DEEP_PAGES` | `0` | 读场景深翻页数（如 40 用于对比首屏 vs 深页） |
| `PERF_THINK` | `0.3` | 迭代间平均停顿秒数 |
| `PERF_VUS1/2/3`、`PERF_STAGE1/2/3` | `10/50/100`、`30s` | 阶梯加压档位 |
| `PERF_HOLD`、`PERF_VUS`、`PERF_WRITE_RATIO` | `30m`、`50`、`0.3` | mixed soak 参数 |

---

## 4. 一条龙命令

```bash
# 0) 进入仓库根
cd _upstream_CPUmodel_V2

# 1) 造数（首次/重建）。默认 10 万任务 / 20 万产物；--quick 为小样自检
python scripts/perf_seed.py --quick        # 快速自检：2 项目 × 100 任务
# python scripts/perf_seed.py              # 正式：20 项目 × 5000 任务 = 10 万任务、20 万产物
# 记下输出里的 PERF_PROJECT_ID / PERF_TOOL_ID / PERF_TOOL_VERSION_ID / 密码，导出为环境变量：
#   export PERF_BASE_URL=http://127.0.0.1:8000/api/v1
#   export PERF_USERNAME=perf_user PERF_PASSWORD=<打印的密码>
#   export PERF_PROJECT_ID=<pid> PERF_TOOL_ID=<tid> PERF_TOOL_VERSION_ID=<tvid>

# 2) 启动后端（另开终端；压测建议多 worker）
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# 3) 冒烟（二选一）
python scripts/perf_load.py --scenario smoke --vus 1 --iterations 1    # 离线
k6 run perf/k6/smoke.js                                                # k6

# 4) 读场景阶梯加压（离线 / k6）
python scripts/perf_load.py --scenario read --vus 50 --duration 120s --deep-pages 40
k6 run perf/k6/read.js

# 5) 写场景（会真实建任务；请用 no-op 工具）
python scripts/perf_load.py --scenario write --vus 20 --duration 60s
k6 run perf/k6/write.js

# 6) 混合 soak（70 读 / 30 写）
python scripts/perf_load.py --scenario mixed --vus 50 --duration 30m --write-ratio 0.3
PERF_HOLD=30m PERF_VUS=50 k6 run perf/k6/mixed.js

# 7) 前后环境快照（EXPLAIN + /metrics）
perf/collect.sh --label before --out perf/results/20261101-1200 --project-id "$PERF_PROJECT_ID"
perf/collect.sh --label after  --out perf/results/20261101-1200 --project-id "$PERF_PROJECT_ID"
```

离线客户端的 `summary.json` 默认写到 `perf/results/<timestamp>/summary.json`（`--out` 可指定），
打印吞吐、P50/P95/P99、错误率与每个 endpoint 的分布，并按 SLO 给出 `PASS/FAIL`。

---

## 5. 看报告

* 离线：`perf/results/<ts>/summary.json`（机器可读）+ 终端 summary；`slo.passed` 为总判定。
* k6：终端 `endpoint` / `thresholds` 汇总；可 `k6 run --out json=perf/results/<ts>/k6.json`。
* 环境快照：`perf/results/<ts>/<label>/` 下的
  `results.explain.txt` / `artifacts.explain.txt` / `tasks.explain.txt` / `workflows.explain.txt`、
  `metrics.txt`、`health.json`、`meta.txt`。

判定透过（对应计划 4.5）：SLO 达标、无内存增长、无连接池耗尽、深页列表不出现大 `TEMP B-TREE`。

---

## 6. SLO（对应计划 4.1）

| 类别 | 指标 | 阈值 |
| --- | --- | --- |
| 读·列表首屏 | P95 | ≤ 300ms |
| 读·详情 | P95 | ≤ 150ms |
| 写·提交任务 | P95 | ≤ 800ms |
| 写·上传（元数据） | P95 | ≤ 1000ms |
| 错误率 | 5xx / 异常占比 | < 0.5%（不含 4xx 业务拒绝） |
| 深页 | 第 1 页 vs 第 5000 页 P95 差异 | ≤ 2× |
| 任务提交→入队 | P95 | ≤ 2s |

---

## 7. 阻塞点 / 注意

* **CSRF**：写请求必须带 `X-CSRF-Token`（值 = `cpumodel_csrf` cookie），否则后端 403
  “CSRF 校验失败”。`k6/lib/auth.js` 与 `scripts/perf_load.py` 已自动处理。
  若改用 `Authorization: Bearer`，后端会跳过 CSRF，但本套按「Cookie + CSRF」真实浏览器路径压测。
* **上传接口**：小文件走 `POST /files/upload`（multipart，字段名 `file`）；分片上传是
  `POST /uploads`（需 `X-Idempotency-Key`）+ `PUT /uploads/{id}/parts/{n}` + `POST /uploads/{id}:complete`，
  本套只压最小的 `POST /files/upload` 元数据路径。
* **提交任务**：`POST /tasks` 会真实创建任务并尝试调度。建议配合 `perf_seed.py` 建的
  no-op 工具（`provider=noop`），避免真实算力消耗；如需真实工具请在测试环境进行。
* **`/metrics` 未接线**：`backend/app/monitoring/prometheus_metrics.py` 已实现 Prometheus 指标与
  middleware，但 `backend/app/main.py` 当前**未注册**该路由/中间件，`GET /metrics` 可能 404。
  `collect.sh` 会降级写说明；启用 Prometheus 采集前需先在 `main.py` 接线。
* **k6 二进制**：不入库（`perf/bin/` 已 gitignore），需自行下载放置。
* **数据库**：造数直连写库，属破坏性准备动作；`--prefix`（默认 `perf_`）保证幂等与可清理，
  清理用 `python scripts/perf_seed.py --clean`。
