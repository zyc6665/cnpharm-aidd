# 中国医药 AIDD 平台：M2/M3 界面落地与研发治理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已就绪的后端域接口（靶点/结构/口袋、化合物/候选物、结果追溯、审计、卡位、SSE）接上可用界面，并补齐 PRD 要求但尚缺的三个后端能力（研发决策记录、项目阶段推导、分片上传会话），使 M1~M3 的验收链路可以在浏览器里走通。

**Architecture:** 前端沿用「api 模块 → domain 纯函数 → views 页面」三层，页面只做编排不写业务判断；后端沿用「models → services（领域用例）→ api/v1（薄路由）」三层，领域服务不自行排队、任务统一走 `create_and_schedule_tool_task`。新增能力只追加表与端点，不改既有契约。

**Tech Stack:** 后端 FastAPI 0.109 + SQLAlchemy 2 async + Alembic + Pydantic v2 + RDKit；前端 Vue 3 `<script setup>` + Vite + ant-design-vue 4 + vue-i18n 9 + molstar 5 + smiles-drawer 2 + vitest 4。

**Spec:** `docs/05-API接口规格说明书.md`（§3.2 阶段、§3.3 决策记录、§4 数据资产与 §4.2 分片上传）、`docs/04-数据模型设计说明书.md`（§5.6 乐观锁、§5.8 upload_session、§9.5 decision_record）、`docs/06-UI交互与原型说明.md`（§3 页面清单 P-06~P-14、P-18~P-20、P-33/P-34、P-36/P-38）、`docs/17-交付仓库与分支策略.md`（§5 步骤表、§7.3 合入流程）

# Global Constraints

- 离线红线：源码与配置**禁止出现任何公网域名、外部 API、遥测上报**（`docs/03` §10 约束 C-1）。`scripts/check_offline_compliance.py` 必须阻断 0。
- 主键一律 `String(36)` UUID（`UUIDMixin`）；时间列 `DateTime` + `default=utcnow`（`TimestampMixin`）。
- 响应统一 `success_response(data)` / `paginated_response(items=, total=, page=, page_size=)`；列表接口**必须分页**，`page: int = Query(1, ge=1)`、`page_size: int = Query(20, ge=1, le=100)`。
- 权限：项目内读写一律走 `backend/app/services/project_access.py` 的 `require_project_role(db, *, project_id, user, allowed_roles)`；写角色 `("owner", "editor")`，读角色 `("owner", "editor", "runner", "viewer")`。
- 领域表只存 `urn` 与 `sha256`，文件内容永远在 `files` 表 + 存储后端（`docs/04` §1）。
- 只追加表（`audit_logs`、`task_input_snapshots`、`decision_records`、`decision_items`）禁止 UPDATE/DELETE，用 ORM 事件守卫兜底（`docs/10` DB-09）。
- 提交信息必须带 `Refs: <PRD 编号或 docs 章节>`；PR 必须先过 8 项 CI 检查再 squash 合入。
- 本机跑后端测试必须 `export PYTHONUTF8=1 PYTHONIOENCODING=utf-8`；前端 vitest 必须 `export TZ=UTC` 且在 `frontend/` 目录下执行 `npx vue-tsc --noEmit -p tsconfig.app.json`。
- 前端零 `any`；新增 i18n 键必须 **zh-CN 与 en-US 同时补齐**。

# Review Focus

- **分页参数越界**：页大小传 1000 或 page=0 时，接口应返回 422 而不是静默截断或返回空页——最容易在照抄 `Query(20)` 时漏掉 `ge/le`。
- **决策快照一致性**：`snapshot` 里的 `candidateId` 若不属于 `subjectId`（候选集），必须 422 拒绝，而不是写入一个指向别处候选的快照。
- **跨项目越权**：靶点/结构/口袋/候选物/结果页面用 URL 里的 id 直达时，若该 id 属于别的项目，必须 404（不暴露存在性），而不是 403。
- **空态与错态**：项目下 0 个靶点、结构无口袋、候选集为空、导入 0 行成功时，页面必须给出可操作的空态而不是白屏或 `NaN`。
- **长任务刷新**：SSE 断开或任务终态后，页面不得残留 5s 轮询（`useTaskDetailLiveUpdates` 的 `stopRefresh` 语义），避免若干标签页累积请求。
- **迁移链单一 head**：两个并行后端 PR 各自 `down_revision = "20261026_04"`，必须有 merge 迁移收敛，否则 `alembic upgrade head` 直接报 multiple heads。

---

# §0 现状盘点（2026-10-25，实测）

## 后端已就绪（10 个 PR 合入，main = `8559f50`）

| 能力 | 入口 | 状态 |
|---|---|---|
| 靶点/蛋白/结构/口袋 | `backend/app/api/v1/targets.py`（15 端点） | 已就绪 |
| 化合物/候选物/候选集 | `backend/app/api/v1/compounds.py`（24 端点） | 已就绪 |
| 结果与追溯包 | `backend/app/api/v1/results.py`（6 端点） | 已就绪 |
| 审计日志 | `backend/app/api/v1/admin_audit.py`（2 端点） | 已就绪 |
| 卡位与队列 | `backend/app/api/v1/gpu.py`（11 端点） | 已就绪 |
| 任务 SSE | `GET /api/v1/tasks/{id}/events` | 已就绪 |
| 工作流 | `backend/app/api/v1/workflows.py`（9 端点） | 已就绪 |

表 48 张，alembic head `20261026_04`，`test/*.py` 217 个，后端 1433 passed（6 failed 全为 Windows 环境差异）。

## 前端缺口（本次要补的主体）

`frontend/src/views/` 只有 admin/auth/error/home/projects/tasks/tools/user/workflow/workspace 十个目录；`frontend/src/api/` **没有** targets / compounds / results / admin-audit / gpu 五个模块。`docs/06` 的 40 个页面里已实现约 12 个，**P-06/P-07/P-08/P-09/P-10/P-11（靶点域 6 页）、P-12/P-13/P-18/P-19/P-20（化合物候选物 5 页）、P-33/P-34/P-36/P-38（结果/算力/审计 4 页）全部缺失**。

## 后端缺口（PRD 要求但未实现）

| 缺口 | Spec | 影响 |
|---|---|---|
| 研发决策记录 `decision_record`/`decision_item` | `docs/05` §3.3、`docs/04` §9.5 | M7 追溯链断在「决定哪个候选往下走」这一环 |
| 项目阶段推导 `GET /projects/{id}/stage` | `docs/05` §3.2 | 项目总览无法告诉用户「下一步该干什么」 |
| 分片上传 `upload_session` | `docs/05` §4.2、`docs/04` §5.8 | >100MB 化合物库无法导入（`docs/04` §13.2 硬要求） |

## 技术债（顺手清）

- `frontend/src/views/projects/Overview.vue:25` 仍有 `/projects/${projectId}/research` 死链（步骤 3 删了路由未删入口，点击 404），`Overview.spec.ts:137-138` 还断言该 href。
- `frontend/src/types/api.d.ts:18` 仍声明 `VITE_WS_URL`（步骤 9 后已无用）。
- `frontend/src/views/admin/Tools.vue:331` `.registration-option--remote` 遗留 CSS。

---

# §1 PR 切分与依赖

六个 PR，边界按**文件所有权**划，不按技术层划。前五个可并行开发，第六个收尾由主线完成。

| # | 分支 | 标题 | 类型 | 迁移 | 依赖 | 预估 |
|---|---|---|---|---|---|---|
| 1 | `feat/decisions-and-stage` | 研发决策记录与项目阶段推导 | 后端 | `20261027_01` | — | 2 天 |
| 2 | `feat/multipart-datasets` | 分片上传会话与数据集登记 | 后端 | `20261027_02` + `20261027_03`(merge) | — | 2 天 |
| 3 | `feat/targets-ui` | 靶点结构域界面（P-06~P-11） | 前端 | — | PR1 的 `/stage` 只读展示，缺失时降级 | 3 天 |
| 4 | `feat/compounds-results-ui` | 化合物候选物与结果界面（P-12/13/18/19/20/33/34） | 前端 | — | — | 3 天 |
| 5 | `feat/admin-compute-audit` | 算力队列与审计日志界面（P-36/P-38） | 前端 | — | — | 1.5 天 |
| 6 | `chore/surface-cleanup` | 死链与残留清理 + 文档同步 | 混合 | — | PR1~PR5 全部合入 | 0.5 天 |

**合入顺序固定：PR1 → PR2 → PR3 → PR4 → PR5 → PR6。**

理由：

- PR1/PR2 各自从 `20261026_04` 分叉，`alembic` 会出现双 head。PR2 额外提交 `20261027_03_merge_decisions_and_uploads.py`（`down_revision = ("20261027_01", "20261027_02")`，`upgrade`/`downgrade` 均为 `pass`），把链收敛回单 head。这样 PR1 与 PR2 可以真正并行，且任意顺序合入后 `alembic upgrade head` 都能跑通。
- PR3/PR4 都改 `router/index.ts`、`domain/projects/navigation.ts`、`locales/{zh-CN,en-US}/index.ts` 三个热点文件，靠**固定插入锚点**把 hunk 拉开（见 §2），使 `git` 能自动合并；若仍冲突，由主线按 §4 的 rebase 流程处理。

## 明确不做（本次范围外）

| 项 | 原因 | 记到哪 |
|---|---|---|
| LDAP / 企业统一认证 | 依赖甲方 AD 环境，`D-04` 待决策项未关闭 | `docs/03B` |
| 虚拟筛选/对接/MD/自由能页面（P-23~P-28） | 依赖 M5 模型资产（Boltz-2 等 9 个未入库） | `docs/17` §5 后续步骤 |
| Boltz-2 工具注册与镜像 | 需 DCU 环境实测 | `docs/08` |
| `X-Idempotency-Key` 请求级幂等表 | 与分片上传解耦，单独一个步骤 | `docs/17` §5.4 未落地清单 |
| MinIO 服务端 Multipart 直传 | 本次用「分片落临时文件 + complete 时拼装」，>256MB 显式报错 | PR2 的 `docs/17` §5.7 段落 |

---

# §2 文件所有权矩阵与共享文件插入锚点

## 所有权（谁新建谁负责，禁止跨 PR 修改）

| 路径 | PR1 | PR2 | PR3 | PR4 |
|---|---|---|---|---|
| `backend/app/models/decisions.py` | 新建 | | | |
| `backend/app/schemas/decisions.py` | 新建 | | | |
| `backend/app/services/decisions.py` | 新建 | | | |
| `backend/app/services/project_stage.py` | 新建 | | | |
| `backend/app/api/v1/decisions.py` | 新建 | | | |
| `backend/alembic/versions/20261027_01_*` | 新建 | | | |
| `backend/app/models/uploads.py` | | 新建 | | |
| `backend/app/schemas/uploads.py` | | 新建 | | |
| `backend/app/services/uploads.py` | | 新建 | | |
| `backend/app/services/datasets.py` | | 新建 | | |
| `backend/app/api/v1/uploads.py` | | 新建 | | |
| `backend/app/api/v1/datasets.py` | | 新建 | | |
| `backend/alembic/versions/20261027_0{2,3}_*` | | 新建 | | |
| `frontend/src/api/targets.ts` | | | 新建 | |
| `frontend/src/types/targets.ts` | | | 新建 | |
| `frontend/src/domain/targets/` | | | 新建 | |
| `frontend/src/views/targets/` | | | 新建 | |
| `frontend/src/api/compounds.ts` | | | | 新建 |
| `frontend/src/api/results.ts` | | | | 新建 |
| `frontend/src/types/compounds.ts` | | | | 新建 |
| `frontend/src/domain/compounds/` | | | | 新建 |
| `frontend/src/views/compounds/` | | | | 新建 |
| `frontend/src/views/results/` | | | | 新建 |
| `frontend/src/api/gpu.ts`、`frontend/src/api/admin-audit.ts` | | | | |
| `frontend/src/types/gpu.ts`、`frontend/src/types/audit.ts` | | | | |
| `frontend/src/domain/admin/compute.ts`、`frontend/src/domain/admin/audit.ts` | | | | |
| `frontend/src/views/admin/Compute.vue`、`frontend/src/views/admin/Audit.vue` | | | | |

> PR5 的所有文件都在「新建」列，与 PR3/PR4 无交集；它与 PR3/PR4 共享的只有 `router/index.ts`、`views/admin/index.vue`、`locales/*`，靠 §2 的锚点错开。

## 共享文件的固定插入锚点（每个 PR 只在自己那一段动手）

**`backend/app/api/v1/__init__.py`**

- PR1：import 块里在 `compounds,` 之后插 `decisions,`；注册块在 `compounds.router` 两行之后插 `api_router.include_router(decisions.project_router, prefix="/projects", tags=["研发决策与阶段"])`。
- PR2：import 块里在 `datasets,` 之后插 `uploads,`（`datasets` 由 PR2 自己新增）；注册块在 `decisions` 两行之后插 `datasets.project_router` 与 `uploads.router`。

**`backend/app/models/__init__.py`**

- PR1：`from app.models.decisions import DecisionItem, DecisionRecord` + `__all__` 末尾 `"DecisionRecord", "DecisionItem",`。
- PR2：`from app.models.uploads import DataFile, Dataset, UploadSession` + `__all__` 末尾 `"UploadSession", "Dataset", "DataFile",`。

**`frontend/src/router/index.ts`**

- PR3：在 `name: 'ProjectSettings'` 那个路由对象**之后**插入 6 条靶点域路由。
- PR4：在 `name: 'WorkflowRunDetail'` 那个路由对象**之后**插入 7 条化合物/结果路由。
- PR5：在 admin 子路由里 `name: 'AdminSystem'` 那个对象**之后**插入 `{ path: 'compute', name: 'AdminCompute', component: () => import('@/views/admin/Compute.vue'), meta: { title: 'admin.compute' } }` 与 `{ path: 'audit', name: 'AdminAudit', component: () => import('@/views/admin/Audit.vue'), meta: { title: 'admin.audit' } }`。

**`frontend/src/views/admin/index.vue`**

- PR5（独占）：`adminTabs` 数组在 `{ key: 'system', ... }` **之前**插入 `{ key: 'compute', icon: DatabaseOutlined, labelKey: 'admin.compute' }` 与 `{ key: 'audit', icon: FileSearchOutlined, labelKey: 'admin.audit' }`，并在 `@ant-design/icons-vue` 的 import 里加这两个图标。PR3/PR4 不改这个文件。

**`frontend/src/domain/projects/navigation.ts`**

- PR3：`ProjectWorkspaceNavKey` 联合类型末尾加 `| 'targets'`；`buildProjectWorkspaceNavItems` 的数组**第 2 项**（`overview` 之后）插入 `{ key: 'targets', label: '靶点与结构', to: /projects/${projectId}/targets }`。
- PR4：`ProjectWorkspaceNavKey` 末尾**再**加 `| 'assets'`；数组**第 4 项之后**（`tasks` 之后）插入 `{ key: 'assets', label: '数据资产', to: /projects/${projectId}/assets }`；`isProjectWorkspaceNavItemActive` **不改**（默认分支已覆盖 `/projects/x/assets/...`）。

**`frontend/src/locales/zh-CN/index.ts` / `en-US/index.ts`**

- PR3：在 `tools: {`（zh 第 904 行 / en 第 905 行）**之前**插入顶层命名空间 `targets: { ... }`。
- PR4：在 `tasks: {`（zh 第 1084 行 / en 第 1085 行）**之前**插入顶层命名空间 `compounds`、`candidates`、`results`。
- PR5：在 `admin: {`（zh 第 1339 行 / en 第 1340 行）**内部、`admin.system` 子对象之后**插入 `compute: { ... }` 与 `audit: { ... }` 两组键（同属 `admin` 命名空间，不动顶层结构）。

> 三处锚点分处 904/1084/1339 行附近，相邻至少 180 行，`git` 三方合并可自动完成；即使冲突，也只是「两边都新增」的 trivial 冲突。

---

# §3 任务分解

## Task 1（PR1）：`decision_records` / `decision_items` 模型与迁移

**Files:**

- Create: `backend/app/models/decisions.py`
- Create: `backend/alembic/versions/20261027_01_decision_records.py`
- Modify: `backend/app/models/__init__.py`
- Test: `test/test_decisions_model.py`

**Interfaces:**

- Consumes: `app.database.base.Base/UUIDMixin/TimestampMixin`；`app.models.traceability.reject_bulk_mutation` 的守卫写法。
- Produces:
  - `class DecisionRecord(Base, UUIDMixin, TimestampMixin)` → 表 `decision_records`，列 `project_id: str`、`decision_point: str`、`subject_type: str`、`subject_id: str`、`reason: str`、`basis_task_ids: list[str]`、`basis_metrics: dict`、`decided_by: str`、`decided_by_id: str | None`、`decided_at: datetime`；关联 `items`（`cascade="all, delete-orphan"`，`order_by=DecisionItem.snapshot_rank`）。
  - `class DecisionItem(Base, UUIDMixin)` → 表 `decision_items`，列 `decision_id`、`candidate_id: str | None`、`verdict: str`、`snapshot_score: Numeric(10,4) | None`、`snapshot_rank: int | None`、`snapshot_attrs: dict`；`UniqueConstraint("decision_id", "candidate_id", name="uq_decision_items_decision_candidate")`；`Index("ix_decision_items_decision_verdict", "decision_id", "verdict")`。
  - 常量 `DECISION_POINTS = ("DP1","DP2","DP3","DP4","DP5")`、`DECISION_SUBJECT_TYPES = ("TARGET","POCKET","CANDIDATE_SET","STRUCTURE")`、`DECISION_VERDICTS = ("SELECTED","EXCLUDED")`。
  - 两个模型都注册 `event.listen(..., "before_update"/"before_delete", _reject_mutation)`。

- [ ] **Step 1: 写失败测试**

```python
# test/test_decisions_model.py
async def test_decision_record_rejects_update(db_session):
    record = DecisionRecord(project_id="p1", decision_point="DP3", subject_type="CANDIDATE_SET",
                            subject_id="s1", reason="ok", decided_by="zyc", decided_at=utcnow())
    db_session.add(record); await db_session.flush()
    record.reason = "改主意了"
    with pytest.raises(ImmutableRecordError):
        await db_session.flush()
```

- [ ] **Step 2: 跑测试确认失败** — `python -m pytest test/test_decisions_model.py -v`，期望 `ModuleNotFoundError: app.models.decisions`。
- [ ] **Step 3: 实现模型与迁移** — 迁移 `revision="20261027_01"`、`down_revision="20261026_04"`（两个并行后端 PR 必须约定同一 base，统一用 `20261026_04`）。
- [ ] **Step 4: 跑测试确认通过** — 期望 2 passed。
- [ ] **Step 5: 验证迁移** — `rm -f /tmp/d1.db && DATABASE_URL="sqlite+aiosqlite:////tmp/d1.db" python -m alembic -c alembic.ini upgrade head`，期望 50 张表且含 `decision_records`、`decision_items`。
- [ ] **Step 6: 提交** — `git commit -m "feat(decision): 新增决策记录与成员快照表（只追加）"`，body 带 `Refs: docs/04 §9.5, docs/05 §3.3`。

## Task 2（PR1）：决策记录领域服务与接口

**Files:**

- Create: `backend/app/schemas/decisions.py`
- Create: `backend/app/services/decisions.py`
- Create: `backend/app/services/project_stage.py`
- Create: `backend/app/api/v1/decisions.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `test/test_decisions_api.py`

**Interfaces:**

- Consumes: `require_project_role`、`success_response`/`paginated_response`、`ValidationException`/`NotFoundException`、`domain_compounds.load_candidate_set`/`serialize_candidate`、`domain_targets.load_target`/`load_pocket`/`load_structure`。
- Produces:
  - `DECISION_READ_ROLES = ("owner","editor","runner","viewer")`、`DECISION_WRITE_ROLES = ("owner","editor","runner")`。
  - `async def create_decision(db, *, project_id: str, user: User, data: DecisionCreate) -> DecisionRecord`
  - `async def list_decisions(db, *, project_id: str, page: int, page_size: int, decision_point: str | None = None) -> tuple[list[DecisionRecord], int]`
  - `def serialize_decision(record: DecisionRecord) -> dict`（含 `items: [{candidate_id, verdict, snapshot_score, snapshot_rank, snapshot_attrs}]`）
  - `async def compute_project_stage(db, *, project_id: str) -> dict`
  - 路由：`project_router`（无 prefix，由 `__init__.py` 挂 `/projects`）提供 `GET /{project_id}/stage`、`GET /{project_id}/decisions`、`POST /{project_id}/decisions`。
- 校验（写进 `DecisionCreate` 的 `@model_validator(mode="after")`）：`selected_ids` 与 `excluded_ids` 不得同时为空；`reason` 去空白后非空；`snapshot` 非空且每个 `candidate_id` 唯一。

- [ ] **Step 1: 写失败测试**（`test/test_decisions_api.py`，9 个用例）
  1. owner 提交候选集决策 → 成功且返回 `id`、`created_at`；
  2. `snapshot` 里混入不属于该候选集的 `candidate_id` → 422 且 message 含「不属于」；
  3. viewer 提交 → 403；
  4. 非项目成员提交 → 404「研究项目不存在」；
  5. `reason` 全空白 → 422；
  6. `selected_ids` 与 `excluded_ids` 都为空 → 422；
  7. 决策写入后 `audit_logs` 多一条 `decision_create`；
  8. 列表分页：造 3 条，`page_size=2` 时 `len(items)==2`、`total==3`；
  9. 修改/删除决策记录 → 抛 `ImmutableRecordError`。
- [ ] **Step 2: 跑测试确认失败** — 期望 404/`ImportError`。
- [ ] **Step 3: 实现 schema + service + router**。关键点：
  - 校验快照归属：`subject_type == "CANDIDATE_SET"` 时用 `SELECT candidate_id FROM candidate_set_items WHERE set_id = :subject_id`；`TARGET`/`POCKET`/`STRUCTURE` 不校验 `snapshot`。
  - 写库后调 `get_audit_logger().log_data_access(...)`，`action="decision_create"`、`resource_type="decision_record"`。
  - `compute_project_stage` 纯推导：`S0 项目已建` → `S1 靶点已建`（`count(targets)>0`）→ `S2 结构与口袋就绪`（存在 `protein_structures` 且有 `pockets.selected`) → `S3 候选物已生成`（`count(candidates)>0`）→ `S4 已提交计算`（`tasks.status in (RUNNING,SUCCESS)`）→ `S5 已有结果`（`tasks.status == SUCCESS`）；`gaps` 最多 5 条，按阻塞程度排序 `NO_TARGET` > `NO_STRUCTURE` > `NO_POCKET_SELECTED` > `NO_CANDIDATE` > `NO_TASK`。
- [ ] **Step 4: 跑测试确认通过** — 期望 9 passed。
- [ ] **Step 5: 全量回归** — `python -m pytest test/ -q -p no:cacheprovider --tb=line`，失败数不超过基线 6 个 Windows 差异。
- [ ] **Step 6: 提交**。

## Task 3（PR2）：`upload_sessions` / `datasets` / `data_files` 模型与迁移

**Files:**

- Create: `backend/app/models/uploads.py`
- Create: `backend/alembic/versions/20261027_02_upload_sessions_and_datasets.py`
- Create: `backend/alembic/versions/20261027_03_merge_decisions_and_uploads.py`（merge 迁移，`upgrade`/`downgrade` 均为 `pass`）
- Modify: `backend/app/models/__init__.py`
- Test: `test/test_uploads_model.py`

**Interfaces:**

- Produces:
  - `class UploadSession(Base, UUIDMixin, TimestampMixin)` → `upload_sessions`：`project_id`、`created_by`、`declared_filename: String(255)`、`declared_size: BigInteger`、`content_type: String(128)`、`minio_upload_id: String(255) | None`、`object_key: String(512)`、`part_size: Integer`（默认 16777216）、`parts: JSON`（默认 `list`）、`state: String(16)`（默认 `"INITIATED"`）、`expires_at: DateTime`。
  - `class Dataset(Base, UUIDMixin, TimestampMixin)` → `datasets`：`project_id`、`created_by`、`name: String(128)`、`dataset_type: String(32)`、`file_urn: String(512)`、`row_count: Integer`、`import_task_id: String(36) | None`、`summary: JSON`。
  - `class DataFile(Base, UUIDMixin, TimestampMixin)` → `data_files`：`dataset_id`、`urn: String(512)`、`file_name: String(255)`、`file_type: String(32)`、`size_bytes: BigInteger`、`sha256: String(64)`、`storage_tier: String(16)`（默认 `"STANDARD"`）。
  - 常量 `UPLOAD_STATES = ("INITIATED","UPLOADING","COMPLETED","ABORTED","EXPIRED")`、`DATASET_TYPES = ("COMPOUND","PROTEIN","ACTIVITY","LITERATURE","EXPERIMENT")`。
- 迁移 2：`revision="20261027_02"`、`down_revision="20261026_04"`。
- 迁移 3：`revision="20261027_03"`、`down_revision=("20261027_01","20261027_02")`。

- [ ] **Step 1: 写失败测试** — 断言三表可插入、`uq_upload_sessions_object_key` 唯一、`parts` 默认 `[]`。
- [ ] **Step 2: 跑测试确认失败**。
- [ ] **Step 3: 实现模型与两个迁移**。
- [ ] **Step 4: 跑测试确认通过**。
- [ ] **Step 5: 验证迁移链** — `alembic heads` 必须只有一个 head（`20261027_03`）；再 `alembic downgrade base` 退出码 0。
- [ ] **Step 6: 提交**。

## Task 4（PR2）：分片上传会话服务与接口

**Files:**

- Create: `backend/app/schemas/uploads.py`
- Create: `backend/app/services/uploads.py`
- Create: `backend/app/api/v1/uploads.py`
- Modify: `backend/app/config.py`（新增 3 项）
- Test: `test/test_uploads_api.py`

**Interfaces:**

- Consumes: `store_file_bytes`（`app.files.writer`）、`settings.STORAGE_PATH`、`require_project_role`、`success_response`。
- Produces:
  - `UPLOAD_PART_SIZE_BYTES = 16 * 1024 * 1024`、`UPLOAD_SESSION_TTL_HOURS = 24`、`UPLOAD_MAX_OBJECT_BYTES = 2 * 1024 * 1024 * 1024`、`UPLOAD_MAX_ASSEMBLY_BYTES = 256 * 1024 * 1024`。
  - `async def create_upload_session(db, *, project_id, user, data: UploadSessionCreate, idempotency_key: str) -> UploadSession`
  - `async def record_upload_part(db, *, session, part_number: int, content: bytes) -> dict`（**追加**写 `parts`，`content` 落 `Path(settings.STORAGE_PATH) / "_uploads" / session.id / f"{part_number:05d}.part"`）
  - `async def complete_upload_session(db, *, session, user, parts: list[UploadPartRef]) -> FileModel`
  - `async def abort_upload_session(db, *, session) -> None`
  - `def serialize_upload_session(session) -> dict`
- 端点（`router = APIRouter(prefix="/uploads", tags=["分片上传"])`）：`POST ""`（必填 `X-Idempotency-Key` 头）、`PUT /{upload_id}/parts/{part_number}`、`POST /{upload_id}:complete`、`DELETE /{upload_id}`。
- `config.py` 新增 `UPLOAD_PART_SIZE_BYTES: int = 16777216`、`UPLOAD_SESSION_TTL_HOURS: int = 24`、`UPLOAD_MAX_ASSEMBLY_BYTES: int = 268435456`。

- [ ] **Step 1: 写失败测试**（`test/test_uploads_api.py`，10 个用例）
  1. 创建会话返回 `uploadId`/`objectKey`/`partSize==16777216`/`partCount==ceil(size/partSize)`；
  2. 缺 `X-Idempotency-Key` → 422；
  3. 同一 `X-Idempotency-Key` 二次创建返回同一 `uploadId`；
  4. 上报第 3 片后再上报第 1 片，`parts` 按上报顺序**追加**且不覆盖已有项；
  5. 上报超出 `partCount` 的片号 → 422；
  6. complete 少传一片 → 422 且 message 含「缺少分片」；
  7. complete 成功返回 `urn`、`size`、`sha256`，且 `files` 表多一行；
  8. 会话已 `COMPLETED` 后再 PUT → 409；
  9. `DELETE` 后 `state == "ABORTED"`，再 PUT → 409；
  10. 累计分片超过 `UPLOAD_MAX_ASSEMBLY_BYTES` 时 complete → 422 且 message 指向后续 MinIO 直传步骤。
- [ ] **Step 2: 跑测试确认失败**。
- [ ] **Step 3: 实现 schema + service + router**。关键点：`parts` 是 JSON 列，**必须重新赋值再 `flag_modified`**（`from sqlalchemy.orm.attributes import flag_modified`；`session.parts = [*session.parts, entry]; flag_modified(session, "parts")`），否则 SQLAlchemy 不感知原地 append。
- [ ] **Step 4: 跑测试确认通过** — 期望 10 passed。
- [ ] **Step 5: 提交**。

## Task 5（PR2）：数据集登记与查询

**Files:**

- Create: `backend/app/schemas/datasets.py`
- Create: `backend/app/services/datasets.py`
- Create: `backend/app/api/v1/datasets.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `test/test_datasets_api.py`

**Interfaces:**

- Produces：`async def register_dataset(db, *, project_id, user, data: DatasetCreate) -> Dataset`、`async def list_datasets(db, *, project_id, page, page_size, dataset_type=None)`、`async def load_dataset(db, dataset_id)`、`async def delete_dataset(db, *, dataset)`、`serialize_dataset(dataset, *, files=None)`。
- 端点：`project_router`（`GET /{project_id}/datasets`、`POST /{project_id}/datasets`），`router`（`GET /datasets/{dataset_id}`、`DELETE /datasets/{dataset_id}`）。
- 语义：`POST /projects/{id}/datasets` 登记一个已完成的导入结果（`file_urn` + `summary`），**不重新解析文件**——解析仍走既有 `POST /projects/{id}/compounds:import`；`docs/05` §4.1 的 `datasets:import` 异步 taskId 形态记为后续步骤。

- [ ] **Step 1~5** 同前，8 个用例（列表分页、类型筛选、跨项目 404、viewer 403、删除后不再出现在列表、`summary` 原样回读、`row_count` 校验非负、`file_urn` 必须 `file:` 前缀）。
- [ ] **Step 6: 提交**。

## Task 6（PR3）：靶点域 api/types/domain 层

**Files:**

- Create: `frontend/src/api/targets.ts`
- Create: `frontend/src/types/targets.ts`
- Create: `frontend/src/domain/targets/index.ts`、`frontend/src/domain/targets/pockets.ts`
- Test: `frontend/test/targets-domain.test.ts`

**Interfaces:**

- Consumes: `get/post/put/del`（`@/api/request`，全部带 `{ silent: true, retry: 1 }`）。
- Produces:
  - `listTargets(projectId)`、`createTarget(projectId, data: TargetCreateInput)`、`getTarget(targetId)`、`updateTarget`、`deleteTarget`
  - `createProtein(targetId, data)`、`getProtein(proteinId)`
  - `predictStructure(proteinId, data: StructurePredictInput)`、`importStructure(proteinId, data)`、`listStructures(proteinId)`
  - `getStructure(structureId)`、`prepareStructure(structureId)`、`structurePdbUrl(structureId)`（返回 `/api/v1/structures/{id}/pdb`）
  - `listPockets(structureId)`、`predictPockets(structureId)`、`getPocket(pocketId)`、`selectPocket(pocketId, selected: boolean)`、`listPocketResidues(pocketId)`
  - `frontend/src/types/targets.ts`：`TargetSummary`、`ProteinDetail`、`ProteinStructureDetail`、`PocketSummary`、`PocketResidue`，字段名与后端 `serialize_*` 的 snake_case 一致。
  - `frontend/src/domain/targets/pockets.ts`：`sortPocketsByScore(pockets): PocketSummary[]`、`findSelectedPocket(pockets): PocketSummary | null`、`formatPocketCenter(pocket): string`（三位小数）、`pocketScoreTone(score): 'strong' | 'medium' | 'weak'`（`<= -8` / `<= -6` / 其他）。

- [ ] **Step 1: 写失败测试**（`frontend/test/targets-domain.test.ts`，6 个用例：排序降序、`selected` 唯一、center 格式化、tone 三档、空数组、`score=null` 归 `weak`）。
- [ ] **Step 2: 跑测试确认失败** — `export TZ=UTC && cd frontend && npx vitest run test/targets-domain.test.ts`。
- [ ] **Step 3: 实现 api/types/domain**。
- [ ] **Step 4: 跑测试确认通过**。
- [ ] **Step 5: 提交**。

## Task 7（PR3）：靶点域六个页面 + 路由 + 导航 + i18n

**Files:**

- Create: `frontend/src/views/targets/List.vue`（P-06）、`Detail.vue`（P-07）、`Predict.vue`（P-08）、`StructureDetail.vue`（P-09）、`Pockets.vue`（P-10）、`PocketResidues.vue`（P-11）
- Modify: `frontend/src/router/index.ts`（在 `ProjectSettings` 之后插 6 条）、`frontend/src/domain/projects/navigation.ts`、`frontend/src/locales/{zh-CN,en-US}/index.ts`
- Test: `frontend/test/targets-pages-surface.test.ts`

**Interfaces:**

- Consumes：Task 6 的 api + domain；`@/components/projects/ProjectWorkspaceNav`、`@/components/common/AppPageHeader`/`AppErrorState`/`SkeletonList`；`@/components/artifacts/StructureArtifactPreview`（3D，不要新引 molstar）。
- Produces：路由名 `ProjectTargets`、`TargetDetail`、`StructurePredict`、`StructureDetail`、`StructurePockets`、`PocketResidues`；路径 `/projects/:projectId/targets`、`/targets/:targetId`、`/proteins/:proteinId/predict`、`/structures/:structureId`、`/structures/:structureId/pockets`、`/pockets/:pocketId/residues`。
- 每页必含：加载骨架、`AppErrorState` 错态（含「返回项目」链接）、空态文案、`data-testid` 供测试断言。

- [ ] **Step 1: 写失败测试**（`test/targets-pages-surface.test.ts`，8 个用例：6 个视图文件存在；router 源码含 6 个路由名；navigation 含 `'targets'` 键且位于 `overview` 之后；i18n 两文件都含 `targets:` 命名空间；List.vue 含空态文案键；Pockets.vue 含 `selected` 切换调用；PocketResidues.vue 含 `is_key` 渲染；StructureDetail.vue 不含 `import.*molstar`）。
- [ ] **Step 2: 跑测试确认失败**。
- [ ] **Step 3: 实现 6 个页面 + 路由 + 导航 + i18n**。约束：页面内不写业务计算，全部调 `@/domain/targets`；提交预测后 `router.push({ name: 'TaskDetail', params: { id: taskId } })`。
- [ ] **Step 4: 跑测试 + 类型检查** — `npx vitest run test/targets-pages-surface.test.ts` 与 `npx vue-tsc --noEmit -p tsconfig.app.json` 均须通过。
- [ ] **Step 5: 全量前端回归** — `TZ=UTC npx vitest run`，期望全绿。
- [ ] **Step 6: 提交**。

## Task 8（PR4）：化合物/候选物/结果 api 与 domain 层

**Files:**

- Create: `frontend/src/api/compounds.ts`、`frontend/src/api/results.ts`、`frontend/src/types/compounds.ts`、`frontend/src/domain/compounds/`（`index.ts`、`properties.ts`、`compare.ts`）、`frontend/src/domain/results/index.ts`
- Test: `frontend/test/compounds-domain.test.ts`

**Interfaces:**

- Produces（api）：`listCompounds`、`createCompound`、`importCompounds`、`getCompound`、`searchCompounds`、`listCandidates`、`createCandidate`、`getCandidate`、`updateCandidate`、`compareCandidates`、`listCandidateSets`、`createCandidateSet`、`getCandidateSet`、`updateCandidateSet`、`listCandidateSetItems`、`addCandidateSetItems`、`removeCandidateSetItem`、`exportCandidateSet`、`listProjectResults`、`getResult`、`getTraceability`、`exportTraceability`。
- Produces（domain）：`PROPERTY_COLUMNS`（`mol_weight`/`logP`/`TPSA`/`HBD`/`HBA`/`RotB`/`QED`）、`formatPropertyValue(key, value): string`、`buildComparisonMatrix(candidates)`（差异高亮 = 该行取值不全相同）、`candidateLocationLabel(candidate)`、`sortResultsByFinishedDesc(results)`。

- [ ] **Step 1: 写失败测试**（8 个用例：7 列属性顺序、`null` 显示 `-`、QED 三位、MW 三位、矩阵差异高亮命中、全相同不高亮、多肽位置标签、结果按 `finished_at` 降序且 `null` 排后）。
- [ ] **Step 2~4**: 失败 → 实现 → 通过。
- [ ] **Step 5: 提交**。

## Task 9（PR4）：化合物/候选物/结果七个页面 + 路由 + 导航 + i18n

**Files:**

- Create: `frontend/src/views/compounds/Assets.vue`（P-12）、`CompoundDetail.vue`（P-13）、`CandidateSetDetail.vue`（P-18）、`CandidateDetail.vue`（P-19）、`Compare.vue`（P-20）、`frontend/src/views/results/List.vue`（P-33）、`ResultDetail.vue`（P-34）
- Modify: `frontend/src/router/index.ts`（在 `WorkflowRunDetail` 之后插 7 条）、`frontend/src/domain/projects/navigation.ts`、`frontend/src/locales/{zh-CN,en-US}/index.ts`
- Test: `frontend/test/compounds-pages-surface.test.ts`

**Interfaces:**

- 路由名：`ProjectAssets`、`CompoundDetail`、`CandidateSetDetail`、`CandidateDetail`、`CandidateCompare`、`ProjectResults`、`ResultDetail`；路径 `/projects/:projectId/assets`、`/compounds/:compoundId`、`/candidate-sets/:setId`、`/candidates/:candidateId`、`/projects/:projectId/candidates/compare`、`/projects/:projectId/results`、`/results/:taskId`。
- 复用：`@/components/tasks/Smiles2DCell` 渲染 SMILES；`ResultDetail.vue` 复用 `getTraceability`，**不新建第二个追溯组件**。

- [ ] **Step 1: 写失败测试**（9 个用例：7 个视图存在、7 个路由名、`assets` 导航项位于 `tasks` 之后、i18n 三个命名空间齐全、`Compare.vue` 限制 6 个上限、`ResultDetail.vue` 含 `traceability` 与导出按钮、`Assets.vue` 含导入入口、`CandidateSetDetail.vue` 含导出、页面均无 `any`）。
- [ ] **Step 2~5**: 失败 → 实现 → 通过 → 全量 `TZ=UTC npx vitest run` + `vue-tsc`。
- [ ] **Step 6: 提交**。

## Task 10（PR5）：算力队列与审计日志界面（P-36 / P-38）

**Files:**

- Create: `frontend/src/api/gpu.ts`、`frontend/src/api/admin-audit.ts`
- Create: `frontend/src/types/gpu.ts`、`frontend/src/types/audit.ts`
- Create: `frontend/src/domain/admin/compute.ts`、`frontend/src/domain/admin/audit.ts`
- Create: `frontend/src/views/admin/Compute.vue`、`frontend/src/views/admin/Audit.vue`
- Modify: `frontend/src/router/index.ts`（admin 子路由 `AdminSystem` 之后插 2 条）、`frontend/src/views/admin/index.vue`（tabs 插 2 项）、`frontend/src/locales/{zh-CN,en-US}/index.ts`（`admin` 下插 `compute`/`audit` 两组键）
- Test: `frontend/test/admin-compute-audit-surface.test.ts`

**Interfaces:**

- Consumes（api）：`getGpuSlotOverview()` → `GET /api/v1/gpu/slots`；`reportSlotState()` 不在前端调用（仅 Agent）；`getGpuSummary()` → `GET /api/v1/gpu/summary`；`listGpuAllocations()` → `GET /api/v1/gpu/allocations`；`listAuditLogs(params)` → `GET /api/v1/admin/audit-logs`；`getAuditFacets()` → `GET /api/v1/admin/audit-logs/facets`。
- Produces（domain）：
  - `frontend/src/domain/admin/compute.ts`：`SLOT_STATE_TONES: Record<'FREE'|'RESERVED'|'BUSY'|'FAULT'|'BORROWED', 'success'|'processing'|'warning'|'error'|'default'>`、`countSlotsByState(slots): Record<string, number>`、`formatSlotIdentifier(slot): string`（`nodeId/slotId`）、`summarizeSlotCapacity(nodes): { totalSlots, schedulableSlots, byVendor: Record<string, number> }`。
  - `frontend/src/domain/admin/audit.ts`：`AUDIT_ACTION_OPTIONS`（从 `actions` facet 直接映射，不硬编码）、`formatAuditTimestamp(value)`、`describeAuditTarget(row): string`（`${resource_type}/${resource_id}`，缺 `resource_id` 时只显示类型）、`isImmutableAction(action): boolean`（`action` 以 `delete` 结尾时也返回 true 用于提示「只追加」）。

- [ ] **Step 1: 写失败测试**（`frontend/test/admin-compute-audit-surface.test.ts`，9 个用例：2 个视图存在；router 含 `AdminCompute`/`AdminAudit`；`views/admin/index.vue` 的 `adminTabs` 含 `compute`/`audit` 且位于 `system` 之前；i18n zh/en 都含 `admin.compute.title` 与 `admin.audit.title`；`compute.ts` 的 `SLOT_STATE_TONES` 覆盖 5 个状态；`countSlotsByState` 对空数组返回 5 个 0；`audit.ts` 不硬编码动作列表；`Compute.vue` 不含 `reportSlotState`；`Audit.vue` 分页参数带 `page_size` 上限）。
- [ ] **Step 2: 跑测试确认失败** — `export TZ=UTC && cd frontend && npx vitest run test/admin-compute-audit-surface.test.ts`。
- [ ] **Step 3: 实现 api/types/domain/两个页面 + 路由 + tabs + i18n**。约束：`Compute.vue` 展示「卡位网格（按节点分组，状态色块 + 可调度数）+ 节点表」，**不提供任何写操作**（卡位声明随部署版本化，后端也不给写接口）；`Audit.vue` 为只读列表 + facet 筛选（actor/action/result/resource_type/时间范围），分页 `page_size` 上限 100。
- [ ] **Step 4: 跑测试 + 类型检查** — `npx vitest run test/admin-compute-audit-surface.test.ts` 与 `npx vue-tsc --noEmit -p tsconfig.app.json` 均须通过。
- [ ] **Step 5: 全量前端回归** — `TZ=UTC npx vitest run`，期望全绿。
- [ ] **Step 6: 提交**。

## Task 11（PR6）：死链与残留清理 + 文档同步

**Files:**

- Modify: `frontend/src/views/projects/Overview.vue`（删 `open-research` 死链，改指向 `ProjectTargets`）、`frontend/src/views/projects/Overview.spec.ts`、`frontend/src/types/api.d.ts`（删 `VITE_WS_URL`）、`frontend/src/views/admin/Tools.vue`（删 `.registration-option--remote`）、`README.md`、`docs/17-交付仓库与分支策略.md`（§5 步骤表 + 新增 §5.7/§5.8/§5.9）
- Test: `frontend/test/product-surface-pruning.test.ts`（补一条断言 `open-research` 不存在）

- [ ] **Step 1~5**：先改 `Overview.spec.ts` 断言为 `/projects/project-1/targets`；改 `Overview.vue`；补 pruning 断言；跑全量；提交。

---

# §4 并行编排

## 4.1 工作区隔离

```bash
cd D:/workbuddy/中国医药平台项目/_upstream_CPUmodel_V2
echo ".worktrees/" >> .gitignore && git add .gitignore && git commit -m "chore(repo): ignore local worktree directory"
git worktree add .worktrees/pr1-decisions -b feat/decisions-and-stage main
git worktree add .worktrees/pr2-uploads   -b feat/multipart-datasets main
git worktree add .worktrees/pr3-targets   -b feat/targets-ui main
git worktree add .worktrees/pr4-compounds -b feat/compounds-results-ui main
```

每个子智能体只在自己的 worktree 里工作，**绝不跨目录**。前端依赖各 worktree 独立 `npm ci`（Windows 下不要用 `ln -s`）。

## 4.2 子智能体分工（5 个并行）

| 子智能体 | 范围 | worktree / 分支 |
|---|---|---|
| `impl-pr1` | Task 1 + Task 2 | `.worktrees/pr1-decisions` / `feat/decisions-and-stage` |
| `impl-pr2` | Task 3 + Task 4 + Task 5 | `.worktrees/pr2-uploads` / `feat/multipart-datasets` |
| `impl-pr3` | Task 6 + Task 7 | `.worktrees/pr3-targets` / `feat/targets-ui` |
| `impl-pr4` | Task 8 + Task 9 | `.worktrees/pr4-compounds` / `feat/compounds-results-ui` |
| `impl-pr5` | Task 10 | `.worktrees/pr5-admin` / `feat/admin-compute-audit` |

每个子智能体的 prompt 必须自带：仓库路径、worktree 路径、分支名、任务编号、**§2 的插入锚点原文**、Global Constraints、明确要求的验证命令与通过判据、以及「完成后回报：改动文件清单 / 测试命令与输出 / 已知未做项」。**明令不要跨 worktree 改代码，也不要伪造测试通过。**

## 4.3 Code Review（开发完成后逐个派）

每个 PR 推送后派一个**只读 reviewer 子智能体**，review 清单：

1. 是否越界改了别的 PR 拥有的文件；
2. 分页参数是否带 `ge/le`；
3. 跨项目越权是否返回 404（不是 403）；
4. 只追加表是否有 UPDATE/DELETE 路径；
5. i18n 是否 zh/en 双份齐全；
6. 是否有 `any`、`console.log`、公网域名；
7. 迁移 `down_revision` 是否正确、`alembic heads` 是否单头（PR1+PR2 合入后）；
8. 测试是否覆盖 Review Focus 的 6 条。

reviewer 输出格式：`BLOCKER` / `SHOULD` / `NIT` 三级 + 文件:行号 + 具体改法。BLOCKER 必须修完再合。

## 4.4 合入顺序与冲突处理

```bash
# 1) PR1 合入
gh pr merge <pr1> --repo zyc6665/cnpharm-aidd --squash --delete-branch
git switch main && git pull --ff-only

# 2) PR2 rebase 到新 main（merge 迁移此时与 20261027_01 汇合，heads 收敛为单头）
cd .worktrees/pr2-uploads && git fetch origin && git rebase origin/main && git push --force-with-lease
gh pr merge <pr2> --repo zyc6665/cnpharm-aidd --squash --delete-branch

# 3) PR3/PR4/PR5 同样 rebase 后合入；若 router/locales 冲突，保留双方新增（union），逐条核对路由名与 i18n 键不重名
# 4) PR6 由主线直接做
```

**关键检查点**：每次合入后立即在 main 上跑 `alembic upgrade head` 与 `alembic heads`，并在 CI 全绿后再合下一个。

---

# §5 验收

| 项 | 命令 | 通过标准 |
|---|---|---|
| 后端 flake8 | `python -m flake8 backend/app --select F401,F821,E9` | 零输出 |
| 后端测试 | `python -m pytest test/ -q -p no:cacheprovider` | 失败数 ≤ 6（全为已知 Windows 差异） |
| 迁移链 | `alembic heads` / `upgrade head` / `downgrade base` | 单 head、退出码 0 |
| 前端类型 | `cd frontend && npx vue-tsc --noEmit -p tsconfig.app.json` | exit 0 |
| 前端测试 | `export TZ=UTC && npx vitest run` | 全绿 |
| 前端构建 | `TMPDIR=$(pwd)/.tmp-build npm run build` | 成功 |
| 离线合规 | `python scripts/check_offline_compliance.py` | 阻断 0 |
| 文档链接 | `python scripts/check_doc_links.py` | PASSED |
| CI | 每个 PR 8 项检查 | 全绿后 squash 合入 |
