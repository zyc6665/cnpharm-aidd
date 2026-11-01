# 中国医药 AI 药物研发平台

面向中国医药健康产业股份有限公司 AI 提效工程建设一期项目的企业级 AIDD（AI-Driven Drug Discovery）平台。

**交付约束**：甲方内网**私有化离线部署**，K8s 承载前后端与平台服务；算力为 2 台 8 卡海光 K100-AI DCU（共 16 卡 / 1024GB HBM2e）；**代码与配置禁止出现任何公网域名、外部 API、遥测上报**。

---

## 1. 这个仓库是什么

本仓库是中国医药交付线的**独立开发仓库**，从自有产品 CPUmodel_V2 的
`develop@ce9a521` 分叉而来，在此之上做领域裁剪与新建。

- **与产品线的关系**：单向、低频。产品线的通用修复可以 cherry-pick 进来；交付线的领域代码**不回灌**产品线。
- **为什么独立成仓**：交付线要删掉约 8900 行产品线专属代码（Agent 对话、远端工具自注册、公网数据库查询），还要改 38 个测试文件；放在产品线里做减法会持续和产品线演进冲突，而交付期只有 3 个月。
- **溯源**：分叉点标签 `cnpharm-base-ce9a521`，详细策略见 [docs/17-交付仓库与分支策略.md](docs/17-交付仓库与分支策略.md)。

## 2. 三分钟上手

```bash
# 1. 克隆（SSH，需已配置 GitHub 密钥）
git clone git@github.com:zyc6665/cnpharm-aidd.git
cd cnpharm-aidd

# 2. 后端依赖（Python 3.11）
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements-dev.txt
cd ..

# 3. 前端依赖（Node 20）
cd frontend
npm ci
cd ..

# 4. 跑一遍基线（提交前必须全绿）
python -m flake8 backend/app --select F401
python -m pytest test/ -v
cd frontend && npm run test && npm run build
```

本地起完整服务（PostgreSQL + Redis + MinIO + 前后端）：

```bash
docker compose -f deploy/compose/docker-compose.dev.yml up -d
```

> 首次启动前需按 `deploy/compose/README.md` 准备 `.env`。**不要把真实密钥提交进仓库**，CI 使用 `ci-only-*` 假值。

## 3. 目录结构

```
backend/            FastAPI 服务端
  app/
    api/v1/         REST 路由（按领域分文件）
    models/         SQLAlchemy ORM
    services/       业务编排
    tasks/          任务队列、状态机、执行器
    execution/      执行后端抽象（ExecutionPort + K8s/SSH 适配器）
    tool_packages/  Tool Package v2 加载、校验、注册
    tool_templates/ 工具模板（含 drug_discovery 领域模板）
    tools/          工具能力注册表与内建工具执行（capabilities/registry/builtin_tools）
  alembic/          数据库迁移（51 个版本）
frontend/           Vue 3 + Vite + ant-design-vue 4
  src/views/        页面（工作台/项目/靶点/化合物/结果/任务/工具/工作流/管理后台）
  src/components/   workflow 画布、artifacts 渲染器
  src/domain/       领域计算（排序、分档、格式化、筛选参数），页面不写业务逻辑
  src/utils/        datetime（服务端时间解析，统一补 Z）等通用工具
deploy/             compose 与 K8s 部署资产
  slots/            卡位声明（slots.yaml，算力节点与卡位映射的事实源）
docs/               中国医药项目文档（00~18，见 docs/README.md）
  archive-upstream/ 产品线历史文档，只读归档
test/               后端测试（260 个文件）
example/            模型资产样例（tool-package v2）
  mock-models/      6 个 mock 模型包（P-15~P-28 的演示驱动，metadata.mock: true）
```

## 4. 分支模型

| 分支 | 用途 | 谁能推 |
|---|---|---|
| `main` | **交付主干**，随时可出包，受保护 | 仅通过 PR |
| `feature/*`、`fix/*`、`refactor/*` | 日常开发，从 `main` 切出 | 开发者 |
| `release/v1.x.y` | 交付候选，只收回归修复 | 发布经理 |
| `cnpharm-base-ce9a521`（tag） | 分叉点锚点，**禁止移动/删除** | 无人 |

工作流：`feature/xxx` → PR → CI 全绿 → approve（团队成形后强制 1 人）→ squash 合入 `main` → 删分支。

> **当前阶段说明**：团队还没拉起来，`main` 的保护规则把 `required_approving_review_count` 设为 `0`——否则唯一开发者无法合入自己的 PR，交付线会直接被锁死。**成员到位后立刻改为 1**，命令见 [docs/17](docs/17-交付仓库与分支策略.md) 第 7 节。管理员约束（`enforce_admins`）始终保持开启：保护规则要约束包括自己在内的所有人。

**每条提交必须带 `Refs:`**，指向需求或决策编号，例如：

```
feat(target): add target entity with protein and protein_structure

新增三张表与迁移，支撑 M2 结构预测任务的归属关系追溯。

Refs: M2-FR-02, 04-数据模型 §6.1~§6.3
```

验收时可用 `git log --grep="M2-FR-06"` 直接列出某个需求条款的全部实现提交。

## 5. 当前状态

基线已就位，靶点域、化合物域、可追溯能力、DCU 卡位调度与实时状态推送已落地（步骤 5~步骤 9），40 个页面**全部有界面**（步骤 10、13、29；其中 11 页由 mock 模型包驱动），分片上传的四条评审阻塞已收口（步骤 12），排队超时巡检与 CI 硬时限兜底已收口（步骤 14），数据版本账本、幂等补挂、项目配额与一处测试泄漏的修正已收口（步骤 15~18）。较需求文档（62 个功能点 / 40 个页面）的差距：

| 类别 | 现状 |
|---|---|
| **可直接复用** | 任务队列/状态机/日志/取消/重试、执行后端抽象（K8s + SSH）、Tool Package v2、Artifact 版本与 lineage、工作流画布（拖拽/连边/条件分支已实现）、molstar 三维渲染 |
| **必须新建** | Boltz-2 等 9 个**真**模型资产（页面与链路已由 6 个 mock 包跑通，替换时只换镜像 tag 与 `metadata.version`）、drp-node-agent 本体、LDAP、`>24h` 超长任务审批标签 |
| **必须删除** | 已于步骤 3、步骤 4 完成：`agents/aidd` Agent 面、`external_databases`、`remote_tools`、`remote_capacity`、`image_registry`、`model_services`（详见下方「已完成的减法」） |

**已完成的减法**（[docs/17](docs/17-交付仓库与分支策略.md) 第 5 节步骤 3、步骤 4）：

- 步骤 3（拆包）：`agents/aidd` 的能力注册表与内建工具迁到 `backend/app/tools/`；Agent 对话/规划/计划审批链路（约 4500 行）连同 `agent_runs`、`conversations` 等 8 张表、前端 `Research` 页面与 Agent 模式标签页一并删除，迁移 `backend/alembic/versions/20261025_01_drop_agent_tables.py`。
- 步骤 4（离线合规）：`external_databases`（公网 PubChem/RCSB/ChEMBL/PDBbind 抓取）、`remote_tools` + `remote_capacity` + `remote_api` 执行器、`image_registry` 死代码、`model_services`（LLM 服务配置）、前端 LLM 预设与产品线品牌外链全部删除；`builtin-fetch-*` / `builtin-query-*` 五个在线工具退场，画布预设 `PubChem 到基础 ADMET` 改为离线可执行的 `配体结构到基础 ADMET`。迁移 `20261025_02_drop_model_services.py`、`20261025_03_remove_external_database_tools.py`。`.github/offline-allowlist.txt` 现为空。

**已完成的加法**（[docs/17](docs/17-交付仓库与分支策略.md) 第 5 节步骤 5~步骤 14）：

- 步骤 5（靶点域）：新增 `targets` / `proteins` / `protein_structures` / `pockets` / `pocket_residues` 五张表与迁移 `backend/alembic/versions/20261026_01_domain_targets_and_pockets.py`；同一结构只允许一个 `selected` 口袋，由分区唯一索引 `uq_pockets_selected_structure` 在数据库层保证。API 覆盖 docs/05 §5 的 15 个端点（项目靶点集合、靶点增删改查、蛋白序列导入与版本、结构导入/预测/准备/导出、口袋登记/预测/选定/残基），领域逻辑集中在 `backend/app/services/domain_targets.py`，任务提交统一走 `create_and_schedule_tool_task`（与单项任务、工作流节点同一执行单元）。

- 步骤 6（化合物域）：新增 `compounds` / `candidates` / `candidate_sets` / `candidate_set_items` / `molecule_fingerprints` 五张表与迁移 `backend/alembic/versions/20261026_02_compounds_and_candidates.py`；化合物是全平台去重主数据（`inchikey` 唯一）而非项目资产，项目视图只列被本项目候选物引用的分子。RDKit 化学层集中在 `backend/app/chemistry/molecule_properties.py`（一次解析出 InChIKey、分子式、分子量与 logP/TPSA/HBD/HBA/RotB/QED，并打包 ECFP4/MACCS 位向量）。API 覆盖 docs/05 §4、§5 的 15 个端点：化合物导入（CSV/TSV/SDF/SMI，InChIKey 去重，解析失败进异常清单不阻断整批，M1-BR-1/BR-2）、化合物登记与相似性检索、候选物增删改查与比较（≤6 并排，M3-FR-08）、候选集与乐观锁（`version` 不匹配返 409 带 `currentVersion`，docs/04 §5.6）、候选集导出 CSV。领域逻辑集中在 `backend/app/services/domain_compounds.py`。

- 步骤 7（可追溯）：新增 `task_input_snapshots` 与 `audit_logs` 两张**只追加**表（迁移 `backend/alembic/versions/20261026_03_traceability.py`），并用 SQLAlchemy 的 `before_update` / `before_delete` 事件守卫在 ORM 层拒绝改写（docs/10 DB-09）；输入快照在 `create_and_schedule_tool_task` 里与任务同事务写入，因此任务一旦存在，输入就已是历史事实。`backend/app/services/traceability.py` 装配 docs/01 §11.2 要求的六类元数据，`GET /api/v1/results/{taskId}/traceability` 一键取回、`POST /api/v1/results/{taskId}:export` 落成 JSON 文件（含内容 sha256）。审计从滚动文件扩展为「文件 + 数据库」双写：`backend/app/services/audit_sink.py` 把 `AuditEvent` 映射进 `audit_logs`，用有界队列异步落库、队列满时丢弃而非阻塞请求（docs/04 §3.2.2 审计失败不阻断业务），管理员经 `GET /api/v1/admin/audit-logs` 按 actor/action/result/资源/时间范围检索。

- 步骤 8（DCU 卡位）：新增 `backend/app/gpu/slots.py`——把 `slots.yaml`（`schemaVersion: 2`，支持 DCU 与 NVIDIA 双形态）解析成「节点 → 卡位 → 设备号/环境变量/镜像/可跑模型」，`accelerator.model` 只做观测展示、不参与调度判定。卡位状态机 `FREE/RESERVED/BUSY/FAULT/BORROWED` 由 drp-node-agent 维护并上报（`POST /api/v1/gpu/slots/report`，独立 token + `hmac.compare_digest`，**不开放在线改声明的写接口**），平台只做消费与调度决策；**Agent 上报 `deviceCount != 1` 时强制置 FAULT**，把 docs/09 §5.6 的 `device_count()==1` 验收纪律落成代码。`GPUAllocation` 增加 `slot_id`/`accelerator_model`/`accelerator_vendor`/`device_ids`/`agent_endpoint`/`image_ref` 六列（迁移 `backend/alembic/versions/20261026_04_gpu_allocation_slots.py`）**只做观测与追溯**，卡位互斥仍由静态声明 + Agent 单队列 + 活动租约唯一索引保证（docs/04 §4.1 明确无 slot 表）。同时修掉一个多节点下的致命缺陷：`GPUAllocator._is_gpu_idle` 原来对任意节点都用本机探针，远程卡位必然抛异常判为忙，导致有声明也分配不出来。`deploy/slots/slots.example.yaml` 随仓交付，是运维照抄的模板。

- 步骤 9（实时推送）：按 [docs/05](docs/05-API接口规格说明书.md) §9 与 [docs/10](docs/10-开发规范与编码约定.md) API-08 用 SSE 替换产品线遗留的 WebSocket。新端点 `GET /api/v1/tasks/{task_id}/events` 返回 `text/event-stream`，帧类型 `snapshot` / `status` / `progress` / `log` / `heartbeat` / `done`；`backend/app/services/task_event_stream.py` 每次被唤醒都开新会话回库重读，因此 worker 与 API 分属不同 Pod 时也能收敛（`test_stream_converges_without_any_notification` 钉住这条）。`backend/app/services/task_event_hub.py` 的队列有界，满了丢弃「有变化」信号而不反压任务执行。前端 `frontend/src/api/task-events.ts` 封装 `EventSource`（`done` 后主动 `close()`），`useTaskDetailLiveUpdates` 连上流就不再轮询、断流才退回 5 秒兜底。删除 `backend/app/websocket/`、`frontend/src/composables/useWebSocket.ts`、`frontend/src/domain/tasks/websocket.ts` 共约 938 行，`WSMessage` 类型与 Vite 的 `/ws` 代理一并退场，管理员统计页的「活动连接数」改为「实时订阅数」。

- 步骤 10（界面落地）：后端接口齐全但页面只有 10 个，这一批补 15 个——P-06~P-11 靶点结构域（列表/详情/结构预测提交/结构详情 3D/口袋列表/口袋残基）、P-12/P-13/P-18/P-19/P-20（数据资产/化合物详情/候选集/候选物详情/候选物比较）与 P-33/P-34（结果中心/结果详情含追溯包导出）、P-36/P-38（算力与队列/审计日志）。同时补齐后端三块：`decision_records`/`decision_items` 两张只追加表与 `POST/GET /projects/{id}/decisions`、`GET /projects/{id}/stage`（S1~S6 纯推导，不引入 `project.stage` 字段）、`upload_sessions` 与 `dataset`/`data_file`/`data_version` 及分片上传四端点。页面只做编排与渲染，排序/分档/格式化/筛选参数拼装一律放 `frontend/src/domain/`。这批工作拆成六个 PR 并行推进，每个都过一遍只读 review，审查清单固定 8 条（越界改文件/分页 `ge,le`/跨项目 404/只追加表无 UPDATE/DELETE/i18n 双份/无 `any` 与 `console.log` 与公网域名/`down_revision` 单头/测试覆盖 Review Focus）。

- 步骤 11（口径统一）：后端时间列全是 **naive UTC**，原来序列化用裸 `isoformat()` 得到 `2026-10-25T13:00:00`，前端 `new Date()` 会按本地时区解释——东八区用户看到的每个时间都晚 8 小时。现在 `isoformat_utc()` 统一补 `Z`（`domain_targets` / `domain_compounds` / `traceability` / `admin_audit` 四处），前端新增 `frontend/src/utils/datetime.ts` 的 `parseServerDate`/`formatServerDateTime` 并让 `formatAdminDateTime` 委托它；审计日志的时间范围筛选也在比较前把 aware 入参归一到 naive UTC，否则 PostgreSQL 会按会话时区隐式转换、窗口偏 8 小时。顺带清掉三处技术债：项目总览页指向已删除的 `/research` 路由的死链、`VITE_WS_URL` 残留声明、`Tools.vue` 的 `.registration-option--remote` 遗留样式。

- 步骤 12（分片上传收口）：PR2 合入时带着四条 reviewer 阻塞，都会在生产规模下暴露——`upload_sessions.parts` 是 JSON 列只能整列读写，三个并发 `PUT /parts` 会互相覆盖，最后只留一片（**字节都在暂存里，索引却丢了**）；幂等键只有普通索引，并发创建会落两行、返回两个 uploadId；分片直写 `STORAGE_PATH/_uploads/` 绕过 `StorageBackend`，生产强制 minio 且容器不挂卷时重启即丢；`expires_at` 只写不校验、`EXPIRED` 全仓只有枚举定义。收口方式：分片索引搬进 `upload_parts`（`(session_id, part_number)` 复合主键 + `ON CONFLICT DO UPDATE`）、加 `uq_upload_sessions_project_idem` 并捕获 `IntegrityError` 重查、新增 `backend/app/files/part_staging.py` 按 `STORAGE_BACKEND` 选本地或对象存储暂存、三个业务入口统一 `_require_active` 拦截并新增 `UploadSessionSweepLoop` 挂 lifespan 兜底。顺带把合并改成流式（原 `bytearray` 拼装 2GB 要常驻 2GB 内存）、校验总字节数、把客户端声明的 `sha256` 落库并校验（`declared_sha256`，对应 docs/05 §4.2 的 42205）、合并上限 256MB 放宽到 2GB。迁移 `backend/alembic/versions/20261028_01_upload_parts_and_idempotency.py` 会**搬数据**：把旧 JSON 里的每条分片迁进新表后才删列，可重复执行且不丢已收到的索引。

- 步骤 13（三项缺口收口）：补 P-39 决策记录页（后端 `/projects/{id}/decisions` 早已就绪，是唯一的「有接口没页面」）、任务状态五态→七态（加 `QUEUED` 与 `TIMEOUT`，后者与 `FAILURE` 的重试策略不同，混在一起会让「超时」被当成「代码错」重试）、请求级 `X-Idempotency-Key` 幂等表（`idempotency_keys` 以 `(scope, key)` 复合主键，`idempotent_route` 装饰器挂在 `POST /api/v1/tasks`）。

- 步骤 14（排队超时巡检）：队列一旦停止消费，任务会永远挂在 `QUEUED`——页面显示「排队中」而实际永远不会开始，用户看不到失败也就不会重试，运维看队列深度还正常，比直接失败更难排查。`backend/app/services/queue_timeout.py` 以 `extra_data["queued_at"]`（不是 `created_at`）为锚点每 5 分钟扫一批，超 `TASK_QUEUE_TIMEOUT_SECONDS`（默认 6 小时）置 `TIMEOUT` 并释放资源预约、推 SSE。同一步还暴露并修掉一处 CI 永久挂死：`while True` + 只靠 `cancel()` 退出且循环体无挂起点的后台循环，会让事件循环被占满、测试内超时也投递不进去，只能靠 CI 层 `timeout-minutes` 兜底。

首轮改造的 14 步提交切分见 [docs/17-交付仓库与分支策略.md](docs/17-交付仓库与分支策略.md) 第 5 节。

## 6. 关键文档入口

新人按角色读，不要从头啃 23 份：

| 你的角色 | 先读这些 |
|---|---|
| **刚进项目** | [docs/README.md](docs/README.md) 的「阅读顺序建议」 |
| **后端** | [03 系统架构](docs/03-系统架构设计说明书.md) → [04 数据模型](docs/04-数据模型设计说明书.md) → [05 API](docs/05-API接口规格说明书.md) → [10 开发规范](docs/10-开发规范与编码约定.md) |
| **前端** | [06 UI 交互](docs/06-UI交互与原型说明.md) → [05 API](docs/05-API接口规格说明书.md) |
| **算法/计算** | [07 模型交付与运行规范](docs/07-模型交付与运行规范.md)（3.6 节 `drp-runner` 是 IO 契约唯一真源）→ [08 DCU 复现](docs/08-DCU适配复现与验证计划.md) → [09 算力节点](docs/09-算力节点与模型运行部署方案.md) |
| **运维/实施** | [13 部署](docs/13-部署架构与上线方案.md) → [14 运维监控](docs/14-运维监控与应急手册.md) → [15 备份恢复](docs/15-数据备份与恢复方案.md) |
| **项目管理** | [01 PRD](docs/01-PRD产品需求文档.md) → [03B 待决策总表](docs/03B-待决策与阻塞项总表.md)（**每周过一遍**）→ [18 验收报告](docs/18-项目验收报告.md)（**缺口与偏差的完整清单**） |

## 7. 协作约定

见 [CONTRIBUTING.md](CONTRIBUTING.md)。要点：

- 开工前认领 Issue，不要直接开分支写代码；
- PR 描述必须填 `.github/pull_request_template.md`，含「影响模块」与「测试结果」；
- 涉及需求口径变更，先改文档再改代码；
- **不要 `git push --force` 到共享分支**；
- CI 红了先修 CI，不要绕过。

## 8. 联系

- 仓库管理员：[@zyc6665](https://github.com/zyc6665)
- 阻塞项登记：Issue 标签 `blocker`，并同步到 [docs/03B](docs/03B-待决策与阻塞项总表.md)
