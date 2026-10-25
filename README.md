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
  alembic/          数据库迁移（28 个版本）
frontend/           Vue 3 + Vite + ant-design-vue 4
  src/views/        页面（工作台/项目/任务/工具/工作流/管理后台）
  src/components/   workflow 画布、artifacts 渲染器
deploy/             compose 与 K8s 部署资产
docs/               中国医药项目文档（00~17，见 docs/README.md）
  archive-upstream/ 产品线历史文档，只读归档
test/               后端测试（216 个文件）
example/            模型资产样例（tool-package v2）
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

基线已就位，靶点域与化合物域已落地（步骤 5、步骤 6）。较需求文档（62 个功能点 / 40 个页面）的差距：

| 类别 | 现状 |
|---|---|
| **可直接复用** | 任务队列/状态机/日志/取消/重试、执行后端抽象（K8s + SSH）、Tool Package v2、Artifact 版本与 lineage、工作流画布（拖拽/连边/条件分支已实现）、molstar 三维渲染 |
| **必须新建** | 其余领域表（audit_log / task_input_snapshot / upload_session / dataset / decision_record）、Boltz-2 等 9 个模型资产、DCU 卡位调度、LDAP + audit_log、追溯包导出、40 个页面中的 30+ |
| **必须删除** | 已于步骤 3、步骤 4 完成：`agents/aidd` Agent 面、`external_databases`、`remote_tools`、`remote_capacity`、`image_registry`、`model_services`（详见下方「已完成的减法」） |

**已完成的减法**（[docs/17](docs/17-交付仓库与分支策略.md) 第 5 节步骤 3、步骤 4）：

- 步骤 3（拆包）：`agents/aidd` 的能力注册表与内建工具迁到 `backend/app/tools/`；Agent 对话/规划/计划审批链路（约 4500 行）连同 `agent_runs`、`conversations` 等 8 张表、前端 `Research` 页面与 Agent 模式标签页一并删除，迁移 `backend/alembic/versions/20261025_01_drop_agent_tables.py`。
- 步骤 4（离线合规）：`external_databases`（公网 PubChem/RCSB/ChEMBL/PDBbind 抓取）、`remote_tools` + `remote_capacity` + `remote_api` 执行器、`image_registry` 死代码、`model_services`（LLM 服务配置）、前端 LLM 预设与产品线品牌外链全部删除；`builtin-fetch-*` / `builtin-query-*` 五个在线工具退场，画布预设 `PubChem 到基础 ADMET` 改为离线可执行的 `配体结构到基础 ADMET`。迁移 `20261025_02_drop_model_services.py`、`20261025_03_remove_external_database_tools.py`。`.github/offline-allowlist.txt` 现为空。

**已完成的加法**（[docs/17](docs/17-交付仓库与分支策略.md) 第 5 节步骤 5、步骤 6）：

- 步骤 5（靶点域）：新增 `targets` / `proteins` / `protein_structures` / `pockets` / `pocket_residues` 五张表与迁移 `backend/alembic/versions/20261026_01_domain_targets_and_pockets.py`；同一结构只允许一个 `selected` 口袋，由分区唯一索引 `uq_pockets_selected_structure` 在数据库层保证。API 覆盖 docs/05 §5 的 15 个端点（项目靶点集合、靶点增删改查、蛋白序列导入与版本、结构导入/预测/准备/导出、口袋登记/预测/选定/残基），领域逻辑集中在 `backend/app/services/domain_targets.py`，任务提交统一走 `create_and_schedule_tool_task`（与单项任务、工作流节点同一执行单元）。

- 步骤 6（化合物域）：新增 `compounds` / `candidates` / `candidate_sets` / `candidate_set_items` / `molecule_fingerprints` 五张表与迁移 `backend/alembic/versions/20261026_02_compounds_and_candidates.py`；化合物是全平台去重主数据（`inchikey` 唯一）而非项目资产，项目视图只列被本项目候选物引用的分子。RDKit 化学层集中在 `backend/app/chemistry/molecule_properties.py`（一次解析出 InChIKey、分子式、分子量与 logP/TPSA/HBD/HBA/RotB/QED，并打包 ECFP4/MACCS 位向量）。API 覆盖 docs/05 §4、§5 的 15 个端点：化合物导入（CSV/TSV/SDF/SMI，InChIKey 去重，解析失败进异常清单不阻断整批，M1-BR-1/BR-2）、化合物登记与相似性检索、候选物增删改查与比较（≤6 并排，M3-FR-08）、候选集与乐观锁（`version` 不匹配返 409 带 `currentVersion`，docs/04 §5.6）、候选集导出 CSV。领域逻辑集中在 `backend/app/services/domain_compounds.py`。

首轮改造的 9 步提交切分见 [docs/17-交付仓库与分支策略.md](docs/17-交付仓库与分支策略.md) 第 5 节。

## 6. 关键文档入口

新人按角色读，不要从头啃 22 份：

| 你的角色 | 先读这些 |
|---|---|
| **刚进项目** | [docs/README.md](docs/README.md) 的「阅读顺序建议」 |
| **后端** | [03 系统架构](docs/03-系统架构设计说明书.md) → [04 数据模型](docs/04-数据模型设计说明书.md) → [05 API](docs/05-API接口规格说明书.md) → [10 开发规范](docs/10-开发规范与编码约定.md) |
| **前端** | [06 UI 交互](docs/06-UI交互与原型说明.md) → [05 API](docs/05-API接口规格说明书.md) |
| **算法/计算** | [07 模型交付与运行规范](docs/07-模型交付与运行规范.md)（3.6 节 `drp-runner` 是 IO 契约唯一真源）→ [08 DCU 复现](docs/08-DCU适配复现与验证计划.md) → [09 算力节点](docs/09-算力节点与模型运行部署方案.md) |
| **运维/实施** | [13 部署](docs/13-部署架构与上线方案.md) → [14 运维监控](docs/14-运维监控与应急手册.md) → [15 备份恢复](docs/15-数据备份与恢复方案.md) |
| **项目管理** | [01 PRD](docs/01-PRD产品需求文档.md) → [03B 待决策总表](docs/03B-待决策与阻塞项总表.md)（**每周过一遍**） |

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
