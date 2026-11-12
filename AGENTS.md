# AGENTS.md — 开发与接手手册

面向两类读者：**新加入的团队成员**，以及在仓库里工作的 **AI Agent**。读完这份应该能独立跑起来、知道改动边界在哪、不踩已知的坑。

> 分工：`README.md` 是「三分钟上手」，[CONTRIBUTING.md](CONTRIBUTING.md) 是提交与评审流程，[docs/internal/30-团队协作与域划分.md](docs/internal/30-团队协作与域划分.md) 是「谁负责什么」，[docs/10-开发规范与编码约定.md](docs/10-开发规范与编码约定.md) 是代码风格。本文只写**怎么做、别做什么**。

---

## 1. 项目是什么

中国医药 AI 药物研发平台（AIDD），面向甲方 AI 提效一期工程。交付形态是**内网私有化离线部署**：K8s 承载前后端与平台服务，算力为 2 台 8 卡海光 K100 DCU。

**三条硬约束，任何时候都不能破：**

1. **离线**：代码、配置、依赖里不能出现公网域名、外部 API、遥测上报。CI 的「离线合规扫描」会拦。
2. **交付线独立**：本仓库从自有产品 CPUmodel_V2 的 `develop@ce9a521` 分叉，只做领域裁剪，领域代码**不回灌**产品线。
3. **单仓多域**：4 个人在同一仓库上改不同业务域，靠目录边界 + 契约层串行化来控制冲突（见第 6 节与 `docs/internal/30`）。

---

## 2. 仓库地图

| 目录 | 内容 | 归属 |
|---|---|---|
| `backend/app/api/v1/` | 31 个路由模块，API 入口 | 按域分（D1–D8） |
| `backend/app/services/` | 94 个业务服务模块，**绝大多数业务逻辑在这里** | 按域分 |
| `backend/app/tasks/`、`execution/`、`worker/`、`gpu/` | 任务状态机、执行器、Celery、卡位调度（合计 ~17k 行） | **L1 执行调度**（平台层，单人负责） |
| `backend/app/models/`、`alembic/` | ORM 模型与迁移（75 个迁移） | **契约层**，改动要单独 PR |
| `backend/app/tool_templates/` | 12 个工具 YAML 模板 | **契约层** |
| `frontend/src/views/`、`components/` | Vue 3 页面与组件（workflow/tasks/tools 三个目录最大） | 按域分 |
| `frontend/src/locales/` | 中英双语，两个 `index.ts` 各 3340 行 | **汇聚点**，改前先看第 6 节 |
| `frontend/src/router/index.ts` | 476 行单体路由表 | **汇聚点** |
| `deploy/` | compose（dev/prod/k100-test）、k8s 清单、node-agent 部署 | **L2 部署算力** |
| `scripts/` | 校验、迁移、性能、环境脚本 | **契约层**（公共工具） |
| `docs/` | 交付文档集，先看 [docs/README.md](docs/README.md) | 全队 |
| `test/` | 290 个后端测试文件 | 全队 |

**没有 Makefile**：`docs/10` §12.2 提到的 `make` 目标、`packages/drp_compute`、`deploy/dev/` 属于产品线口径，本仓库不存在。**以仓库实际目录为准**。

---

## 3. 技术栈（实测版本，不要照抄旧文档）

| 层 | 组件 |
|---|---|
| 后端 | Python 3.11、FastAPI、SQLAlchemy、Alembic、Celery（worker + beat）、flower |
| 前端 | Vue 3、Vite、ant-design-vue 4、Pinia、vitest、Playwright、Node 20 |
| 数据 | PostgreSQL **16**（`postgres:16-alpine`）、Redis 7、MinIO `RELEASE.2024-06-13T22-53-53Z` |

> `docs/04` 里写的 PostgreSQL 15 是早期口径；以 compose 与集群清单里的 16 为准。

---

## 4. 环境：数据集中，应用各本地

**数据服务跑在 4090 节点**（k3s，namespace `cnpharm-aidd`），**后端 / worker / beat / 前端跑在各自机器**：

| 服务 | 地址 | 说明 |
|---|---|---|
| PostgreSQL | `10.202.2.228:30432` | 库 `scitool`，用户 `scitool` |
| Redis | `10.202.2.228:30379` | 带密码 |
| MinIO | `10.202.2.228:30900` / 控制台 `:30901` | 默认桶含 `scitool-files` 等 7 个 |
| 后端 | 本地 `:8000` | uvicorn |
| 前端 | 本地 `:5173` | vite dev server |

首次接入只需改 `backend/.env` 的 6 行（`DATABASE_URL`、`MINIO_ENDPOINT`、`REDIS_HOST`、`CELERY_BROKER_URL`、`CELERY_RESULT_BACKEND`、`K8S_ADAPTER_OBJECT_STORAGE_ENDPOINT`），口径见 `docs/internal/30` §8。

### 启动顺序

```bash
# 1. 后端
cd backend && . .venv/Scripts/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 2. worker —— 8 个队列必须全覆盖，漏一个任务就永远排队
celery -A app.worker.celery_app worker --pool=threads --concurrency=4 \
  -Q high_priority,gpu_queue,heavy_compute,cpu_queue,default,tool_tasks,maintenance,monitoring

# 3. beat（定时任务）
celery -A app.worker.celery_app beat

# 4. 前端
cd frontend && npm run dev
```

Windows 上 `--pool=threads`，**不要用 `solo`**（会串行卡死）。8 个队列名写错或漏写，前端表现为「任务一直排队、`worker_available=false`」。

### 自检

```bash
curl http://127.0.0.1:8000/api/v1/system/health     # celery 项应为 healthy
```

任务详情里 `dispatch.worker_available` 为 `true` 才算 worker 接上了。

---

## 5. 命令速查

| 目的 | 命令 |
|---|---|
| 后端静态检查 | `python -m flake8 backend/app --select F401` |
| 后端测试 | `python -m pytest test/ -v` |
| 前端测试 + 构建 | `cd frontend && npm run test && npm run build` |
| 前端 E2E | `cd frontend && npm run test:e2e -- --project=chromium --reporter=list --workers=1` |
| 迁移升级 / 回滚 | `cd backend && python -m alembic upgrade head` / `python -m alembic downgrade base` |
| 离线合规 | `python scripts/check_offline_compliance.py` |
| 文档链接 | `python scripts/check_doc_links.py` |
| 注册新工具 | `python scripts/create_tool.py`（字段见 `docs/internal/28`） |
| 本地中间件（可选） | `scripts/dev_middleware_up.sh`（无 4090 访问权时的退路） |

CI（`.github/workflows/ci.yml`）跑 10 个作业：后端规范、后端测试、迁移链、前端构建、前端单元测试、前端 E2E、离线合规、部署配置校验、依赖漏洞审计、文档链接。**本地能过再提 PR**，不要指望 CI 帮你发现。

---

## 6. 改动边界：什么必须单独走

### 6.1 契约层（改动要单独 PR，提前一天在群里报，指定一人合）

- `backend/alembic/versions/` — 迁移取号前先说明，避免撞号；命名 `YYYYMMDD_NN_主题.py`，**必须写可用的 `downgrade()`**
- `backend/app/api/v1/__init__.py` — 路由注册表
- `backend/app/services/platform_tool_seeding.py` — 10 个平台工具 slug 与时限的**唯一真源**（`REQUIRED_TOOL_SLUGS` / `TOOL_TIMEOUT_MINUTES`，gromacs-md 4320 分钟、pocket2mol 720、boltz2 各 360、多数 240、默认 60）
- `backend/app/tool_templates/` — 工具模板 YAML
- `docs/05-API接口规格说明书.md` — 接口契约
- `.github/`、`deploy/`、`scripts/` — 门禁、部署与公共脚本

### 6.2 汇聚点（一次改一处，改完立刻提交，双语必须同改）

| 文件 | 现状 | 怎么改 |
|---|---|---|
| `frontend/src/locales/zh-CN/index.ts` + `en-US/index.ts` | 各 3340 行，近 300 提交里改动最频繁（各 72 次） | **两个文件必须同一次提交**，键名一致，缺键会让 en 界面显示原始 key |
| `frontend/src/router/index.ts` | 476 行单体 | 加路由只在末尾追加，别重排 |
| `backend/app/config.py` | 全局配置，26 次改动 | 新增配置项要同时改 `.env.example` 与部署清单 |
| `frontend/src/types/models.d.ts` | 全局类型 | 改字段先确认后端 schema |
| `backend/app/api/v1/__init__.py` | 路由表 | 与契约层同流程 |

### 6.3 三个业务域在后端没有独立模块

分子设计 / 亲和力 ADMET / 虚拟筛选（D3–D5）共用 `api/v1/tasks.py`、`api/v1/results.py` 与 `tool_templates/`。**前端按域切、后端按模块切**：预测类域的 owner 拥有自己的 views 与 `tool_templates/` 里的 YAML，但不拥有 `tasks.py` / `results.py`。改这两个文件前先在 Issue 里说一声。

---

## 7. 已知的坑（都是踩过的）

| 坑 | 现象 | 正确做法 |
|---|---|---|
| 配置模块路径 | `from app.core.config import settings` 报 ModuleNotFoundError | 是 **`from app.config import settings`** |
| Git Bash 路径改写 | `pg_dump -f /tmp/x.dump` 被改写成 `C:\...\tmp\x.dump` | 走 stdout 重定向：`pg_dump ... > x.dump` |
| 4090 拉不到 minio 镜像 | `ErrImagePull`，节点默认的公共镜像加速器对 minio 返回 403 | 必须保留 `deploy/k8s-dev/cnpharm-aidd/11-image-4090.yaml`（指向集群内 registry 的镜像） |
| 工具 Pod 回读存储 | 用 `127.0.0.1` 的 MinIO 地址，Pod 在 4090 上连不到 | `K8S_ADAPTER_OBJECT_STORAGE_ENDPOINT` 写内网 IP `http://10.202.2.228:30900` |
| 代理 | `gh auth refresh` / `git clone` 超时，浏览器却正常 | 系统代理只对浏览器生效；设 `HTTP_PROXY`/`HTTPS_PROXY=http://127.0.0.1:10808`，git 侧用 `git config --global http.proxy` |
| 密钥泄漏 | `backend/.env.bak-*` 被提交 | `.gitignore` 只忽略了 `backend/.env`，任何备份文件都放仓库外 |
| 迁移链断裂 | 只写 `upgrade()`，`downgrade()` 报错 | CI 的「迁移链」作业会从 `head` 降到 `base` 再升回来 |

---

## 8. 工作方式（与 CONTRIBUTING 一致，这里是摘要）

- **Issue 是唯一工作单元**：一个 Issue ≤ 2 天工作量，必须写清需求编号（M1–M7）、验收标准、影响的域。没有 Issue 的 PR 不合并。
- **PR**：≤ 400 行、≤ 2 天、只碰一个域；标题 `type(scope): subject`；正文 `Closes #N`；合并方式 squash。
- **分支**：`feature/` `fix/` `refactor/` `docs/` `release/` `spike/`；**活不过 3 天**；谁后合谁 rebase。
- **评审**：1 人通过即可（CODEOWNERS 配好后按域找人）。**不要自己合自己的 PR**。
- **进度**：看板 5 列（Backlog / Ready / In Progress / In Review / Done），In Progress 每人 ≤ 1；每日在 Discussion 的站会帖回 3 行。

---

## 9. 文档治理

- 索引在 [docs/README.md](docs/README.md)（§0.1 编号规则、§10 治理规则）。
- 交付文档放 `docs/` 根，内部记录放 `docs/internal/`，一次性记录放 `docs/archive/`（**只读，不要改**）。
- 新增文档取全局最大号 +1（当前 `31`），命名 `NN-中文标题.md`。
- 改完必须过 `python scripts/check_doc_links.py`，并同步 `docs/README.md` 与 `docs/00` 里的份数。
- `docs/superpowers/specs/2026-10-30-enterprise-ldap-auth-design.md` 被后端代码注释直接引用，**不可移动或改名**。

---

## 10. 给 AI Agent 的额外约定

1. **先读再改**：改动前读 `docs/internal/30` 的域边界表，确认这个文件归谁；跨域改动拆成多个 PR。
2. **不碰别人的 WIP**：工作树里未提交的文件可能属于其他人，不要 `git checkout --`、`git stash` 或删掉它们。用独立 worktree 从 `origin/main` 开工。
3. **不绕过门禁**：不要 `--no-verify`、不要强推、不要为了过 CI 删测试或放宽断言。
4. **迁移必须可回滚**：写 `downgrade()`，本地跑 `upgrade head` → `downgrade base` → `upgrade head`。
5. **报完成前先跑基线**：第 5 节的四件套（flake8 / pytest / npm test / npm build）加上改动相关的检查，贴出实际输出再下结论。
6. **不写死密钥**：`backend/.env` 不进仓库；文档里用 `<密码>` 占位。
7. **文档与代码同批**：改了接口就改 `docs/05`，改了部署就改 `docs/13`/`docs/internal/21`，否则下一个人按旧文档操作。

---

## 11. 新人第一周

| 天 | 做什么 |
|---|---|
| D1 | 读 `README.md` → 本文 → `docs/00`（总纲）→ `docs/02`（需求追踪矩阵）；改好 `backend/.env`，把后端、worker、beat、前端四进程跑起来，`/health` 全绿 |
| D2 | 读 `docs/internal/30`（域划分）+ `docs/03`（架构）+ `docs/05`（接口）；跑一遍基线测试，确认本地全绿 |
| D3 | 认领一个 `Ready` 列的小 Issue（≤ 1 天），走完「切分支 → 小步提交 → PR → 1 人评审 → squash 合并」全流程 |
| D4–D5 | 在自己域内认领一个真实需求（对应 M1–M7 的某条），按 `docs/02` 的验收标准交付 |
