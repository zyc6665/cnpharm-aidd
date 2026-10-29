# 契约收敛 · 项目聚合根 · 产物真值化 实施计划

**Goal**：在不动模型资产、不碰 DCU 的前提下，把「项目归属、权限判定、产物真值、契约一致性」四条地基补上，使平台能支撑「工作流 + 资产 + 追溯」三件事，且后续不再返工。

**Architecture**：不改分层（api → services → models 已干净）。只做四类事：新增单一枚举源与前端 codegen、给 `tasks` 加真外键、把 RBAC 判定收敛到一个矩阵、把产物写入收敛到一个 `ArtifactWriter`。所有改动保持向后兼容：旧数据可读、旧接口签名不变、旧行为有兜底。

**Tech Stack**：FastAPI 0.112 / SQLAlchemy 2 async / Alembic（单 head `20261030_02`）/ Pydantic v2 / Vue3 + Vite + ant-design-vue / PostgreSQL + Redis + MinIO。

**Spec**：
- `docs/04-数据模型设计说明书.md` §5.0（RBAC）、§5.4（audit_log）、§5.6（并发控制）、§9（task/artifact）
- `docs/05-API接口规格说明书.md` §1.2（统一响应体）、§9.2（追溯视图）、§10.1（追溯包）
- `docs/06-UI交互与原型说明.md` P-12（数据资产 Tab = 化合物/蛋白/数据集）
- `docs/10-开发规范与编码约定.md` DB-09（只追加）、API-08（SSE）
- `docs/18-项目验收报告.md` §6.3/§6.4（已登记缺口，本计划不重复其条目）

**Global Constraints**（违反即打回）：
1. 私有化离线内网：不得引入任何公网依赖、不得新增外部服务。
2. 单客户单版本：不做多租户、不做版本并行兼容层、不做灰度开关体系。
3. 迁移必须 `upgrade head` + `downgrade` 双向可执行；必须能在既有数据上回填且可重入。
4. 单 head 必须保持；新迁移号一律 `20261030_03` 起顺延，禁止与在途分支撞号。
5. 只追加表（`audit_logs`、`task_input_snapshots`、`decision_records`）不得 UPDATE/DELETE。
6. 每个 PR 本地必须过：`flake8 backend/app --select F401,F821,E9`、`pytest test/`（Windows 允许 6 个已知差异）、`npx vue-tsc -p tsconfig.app.json`、`npx vitest run`（`TZ=UTC`）、`check_doc_links.py`、`check_offline_compliance.py`。
7. 提交信息必须带 `Refs:` 指向本计划小节或 docs 条款。

**Review Focus**（每个 PR 的 reviewer 必看）：
1. 迁移能否在「有历史数据」和「空库」两种情况下都跑通，且 `downgrade` 不丢数据。
2. 是否有调用方因为签名/语义变化而静默降级（尤其 `Task.project_id` 从 property 变 column）。
3. 新增的唯一约束/幂等键，是否会让既有合法数据插入失败。
4. 前端枚举是否与后端 Literal 逐值一致（codegen 后应有守护测试）。
5. 权限改动是否出现「比原来更宽」的路径（越权比缺权更危险）。
6. 响应信封改造后，前端是否所有读 `.data` 的地方仍然成立。

---

## §0 现状基线（实测，main `ae3a788` 前）

| 项 | 数值 | 取证方式 |
|---|---|---|
| 裸返回端点（`return {`） | **23** 处 | `grep -rn "^\s*return {" backend/app/api/v1/*.py \| wc -l` |
| `HTTPException` 使用 | users.py 12 / gpu.py 12 / artifacts.py 11 / projects.py 6 / workflows.py 5 … | `grep -rc HTTPException backend/app/api/v1/*.py` |
| `require_project_role(` 调用点 | **34** | grep 排除定义 |
| `load_project_membership(` 调用点 | **26** | 同上 |
| `set_task_project_id(` 调用点 | **2** | 同上（**这是孤儿任务的直接证据**：只有 2 处写项目归属） |
| `Task.project_id` | 无列，仅 property（`models/tasks.py:110-118`） | 读模型 |
| `PAUSED` / `BULK` 实现 | **1** 处命中（基本等于未实现） | grep |
| Artifact 写入路径 | 3 条（上传 `services/artifacts.py`、单任务 `services/standard_artifacts.py`、工作流复用同一条） | 读代码 |
| `link_artifact_lineage` 调用 | **0** | grep |
| 写审计落库的地方 | **5** 处 | grep `get_audit_logger().` |

---

## §1 决策：明确「不做什么」（这一节是本计划最重要的部分）

评审里有若干「看起来该改」的点，改动面极大而客户价值为零或负。**明确不做**，避免返工：

| 候选改动 | 决定 | 理由 |
|---|---|---|
| 把项目角色 `owner/editor/runner/viewer` 改名成文档的 `OWNER/MEMBER/VIEWER` | **不做** | 需改 34 处调用、全部历史数据、前端 5 个文件，收益只是「名字与文档一致」。改为**反向对齐**：把 `docs/04` §4.2 的角色表改成「OWNER→owner、MEMBER→editor\|runner、VIEWER→viewer」的投影说明。代码更细的粒度是优点不是缺陷。 |
| 项目状态补齐 `PAUSED` | **做**（低成本） | `schemas/projects.py` Literal 加 `paused`，`docs/04` 同步；无数据迁移（现有 `draft` 保留为兼容值）。 |
| 任务优先级补 `BULK` | **不做** | 队列实现按 capability 分队列，`BULK` 无消费方；补一个没人用的枚举值只会扩大测试面。改为在 `docs/04` 标注「一期以 normal/high/low 落地，BULK 二期」。 |
| 删除 `get_db` 的隐式二次 commit | **不做**（本计划内） | 大量 handler 依赖隐式提交，删它会一次炸掉几十个端点。只做「不入队先提交」的顺序修正（见 Task 2.3），把隐患登记为技术债。 |
| 把 `TaskOutput` 一次性废弃 | **不做**（本计划内） | 存量结果全部在它上面。改为「新写入只进 Artifact，`TaskOutput` 只读兼容」，并在 `docs/17` 登记退役条件。 |
| 现在做多副本分布式改造（SSE pub/sub、巡检选主） | **不做**（本计划内） | 一期是单副本部署（`docs/13`）。改为：给 4 个 sweep 加**同一把 Redis 选主锁**（复用 `WORKFLOW_RECONCILE_LOCK_KEY` 的同款实现，约 40 行），不做 pub/sub。 |
| 把 158 个「源码字符串断言」全部改成行为断言 | **不做** | 改法是重写测试，风险大于收益。只在新写的测试里禁止源码断言，并在 `CONTRIBUTING.md` 登记。 |

---

## §2 五个 PR 的切分与顺序

| # | 分支 | 内容 | 预估 | 依赖 |
|---|---|---|---|---|
| 1 | `fix/contract-consistency` | 枚举单源 + 前端 codegen + 响应信封 + 异常 handler + 23 处裸返回 + 前端错误读 `detail` + 审计补录（§3.5） | 3d | — |
| 2 | `feat/project-aggregate` | `tasks.project_id` 真列 + 回填 + RBAC 矩阵（admin 旁路 / viewer 只读 / runner 才可提交） + `project.version` | 3-4d | 1 |
| 3 | `refactor/artifact-as-truth` | `ArtifactWriter` 统一三路写入 + DB 生成版本号 + 幂等键 + 血缘自动写 + `ArtifactVersion.source_*` + 校验前置 + 单份存储 + 流式下载 + 分页 | 8-10d | 2 |
| 4 | `fix/execution-hardening` | `blocked` 终结 + run 级超时 + 大产物流式 + drp-runner 契约（`DRP_*`、退出码 10/11/12/13、SIGTERM 上传） + run 快照 tool_version + 节点建任务幂等 | 3-4d | 3 |
| 5 | `feat/asset-unification` | Artifact 作为资产根 + P-12 补「蛋白/数据集」Tab + 资产统一检索 | 3d | 3 |

**只做三件的话**：2 → 3 → 4。

---

## §3 Task 1：契约收敛（`fix/contract-consistency`）

### 3.1 单一枚举源
- 新建 `backend/app/common/enums.py`：集中 `PROJECT_STATUS`、`PROJECT_ROLE`、`TASK_PRIORITY`、`ARTIFACT_TYPE`、`AUDIT_ACTION`、`AUDIT_RESULT`、`RESOURCE_TYPE`，每项带 `values()` 与 `Literal` 类型别名。
- 现有 `models/*.py` 里的枚举类**保留**（避免 import 环、避免一次性改 200 处），但改为从 `common/enums.py` 取 `values()` 做校验；`schemas/*.py` 的 `Literal` 改为引用 `common.enums` 的类型别名。
- `schemas/projects.py` 的 `ProjectStatus` 增加 `"paused"`。
- **Files**：`backend/app/common/enums.py`（新）、`schemas/projects.py`、`schemas/tasks.py`、`schemas/artifacts.py`、`models/tasks.py`（只改默认值来源）。
- **验证**：`grep -rn "Literal\[" backend/app/schemas | wc -l` 应显著下降；每个 `Literal` 只剩一处定义。

### 3.2 前端枚举 codegen
- 新建 `scripts/gen_frontend_enums.py`：读 `backend/app/common/enums.py`（用 `import` 而非正则），输出 `frontend/src/types/enums.generated.ts`，含 `export const PROJECT_STATUS = [...] as const` + `export type ProjectStatus = typeof PROJECT_STATUS[number]`。
- `frontend/src/types/models.d.ts` 里对应的联合类型改为 re-export 自 generated 文件。
- 加守护测试 `test/test_frontend_enum_parity.py`：断言 generated 文件与 `common/enums.py` 逐值一致（跑 codegen 到临时文件再 diff，不改仓库文件）。
- **Files**：`scripts/gen_frontend_enums.py`（新）、`frontend/src/types/enums.generated.ts`（新，入库）、`frontend/src/types/models.d.ts`、`test/test_frontend_enum_parity.py`（新）。

### 3.3 统一异常与响应
- `backend/app/main.py` 新增两个 handler：`HTTPException` → `error_response(message=exc.detail, code=exc.status_code)`；`RequestValidationError` → `error_response(message="请求参数校验失败", code=422, detail=exc.errors())`。
- 保留 `AppException` handler 不变（362 处不动）。
- 23 处裸 `return {` 改为 `success_response(...)`，逐文件改，涉及 `gpu.py`（`/slots`、`/allocations` 已在早前改过，本次只改其余）、`users.py`、`tasks.py`、`admin_audit.py`、`targets.py`、`workspace.py`、`artifacts.py`。
- **同步改对应测试断言**：`test/test_gpu_slots.py`、`test/test_gpu_api.py` 等凡断言裸结构的，改为取 `["data"]`。
- 前端 `frontend/src/api/request.ts:176` 错误消息读 `error.response.data?.detail ?? error.response.data?.message`。
- **Files**：`backend/app/main.py`、7 个 api 文件、`frontend/src/api/request.ts`、约 6 个测试文件。
- **验收**：`grep -rn "^\s*return {" backend/app/api/v1/*.py` 为 **0**；前端 vitest 全绿。

### 3.4 文档
- `docs/04` §4.2 角色表改为投影说明；§4.2 优先级标注 `BULK 二期`；状态补 `PAUSED`。
- `docs/17` §5 新增步骤 17（契约收敛）。

### 3.5 审计补录（自审后补入，属 TC-NFR-04 合规项）
现状只有 5 处落库，登录/登出/登录失败/任务提交/取消/重试/用户与工具管理全无痕，过不了 TC-NFR-04。
- 在 service 层加统一 emit：`api/v1/auth.py` 的 `login`/`logout`/失败分支（`AuditAction.LOGIN/LOGOUT/LOGIN_FAILED`，`actor` 用 email，`result` 用 SUCCESS/FAILURE）；`tasks/service.py` 的 `create_and_schedule_tool_task`（`TASK_SUBMIT`）、`tasks/cancellation.py` 已有（补 `TASK_CANCEL`/`TASK_RETRY` 的 result 与 request_id）；`api/v1/users.py` 与 `api/v1/tools_admin.py` 的用户/工具增删改（`ADMIN_USER_*`/`ADMIN_TOOL_*`）。
- `audit_sink` 队列满时降级为**同步写一行死信表**（新建 `audit_log_deadletters`，只追加），不再纯丢弃；`stop()` 先禁入队再 `await queue.join()` 排空。
- **验收**：新增 `test/test_audit_coverage.py`——逐动作触发后断言 `audit_logs` 有对应 (actor, action, result, resource_id) 行。
- 客户价值的判断依据：`docs/12` TC-NFR-04 明确要求六类动作可查、字段完整、不可篡改；这是验收项，不是"锦上添花"。

---

## §4 Task 2：项目聚合根与 RBAC（`feat/project-aggregate`）

### 4.1 `tasks.project_id` 落真列
- 迁移 `20261030_03_task_project_aggregate.py`：
  - `op.add_column("tasks", sa.Column("project_id", sa.String(36), nullable=True))` + `op.create_index("ix_tasks_project_id", "tasks", ["project_id"])` + `op.create_foreign_key("fk_tasks_project_id", "tasks", "projects", ["project_id"], ["id"], ondelete="SET NULL")`
  - 回填：`UPDATE tasks SET project_id = NULLIF(extra_data::jsonb->>'project_id','') WHERE project_id IS NULL AND extra_data IS NOT NULL`（SQLite 分支用 `json_extract(extra_data,'$.project_id')`）
  - `downgrade` 删 FK/索引/列
- 模型 `backend/app/models/tasks.py`：删 `project_id` property 与 `project_id_expression()` 的 JSON 表达式实现，改为
  ```python
  project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
  @classmethod
  def project_id_expression(cls):  # 保留签名，返回真列
      return cls.project_id
  ```
  `task_context.task_project_id(task)` 改为 `return task.project_id`（保留函数以免 30 处调用方改动）。
- `set_task_project_id(task, project_id)` 改为同时写列与 `extra_data`（双写一个版本周期，防回滚丢数据）。
- **风险点（reviewer 必看）**：`project_id_expression()` 在 `tasks.py`/`results.py`/`project_quotas.py` 里用于 `==` 比较，返回值从 JSON 表达式变 Column 后 SQL 形态变化，需实测 `EXPLAIN` 或用例覆盖；`Task.project_id` 由 property 变 column 后，`Task(project_id=...)` 构造合法（原来是只读 property，任何地方若曾 `task.project_id = x` 会静默失效——grep 确认无赋值）。

### 4.2 RBAC 矩阵
- 新建 `backend/app/services/rbac.py`：
  ```python
  PROJECT_ROLE_RANK = {"viewer": 1, "runner": 2, "editor": 3, "owner": 4}
  PROJECT_ACTIONS = {
      "read": {"viewer"}, "run": {"runner", "editor", "owner"},
      "write": {"editor", "owner"}, "admin": {"owner"},
  }
  def role_allows(role, action) -> bool
  async def require_project_action(db, *, project_id, user, action) -> tuple[Project, ProjectMember]  # admin bypass
  ```
- `services/project_access.py` 的 `require_project_role` **保持签名**，内部改为：`admin` 旁路 → `require_project_action(action=...)`（由 `allowed_roles` 反查最小 action，或直接保留集合语义但加 admin 旁路）。
  - **最小实现**：只做两件事——① admin 旁路 ② 集合比较前把 `admin` 视为 `owner`。34 处调用点数不变。
- 修「viewer 能提交任务」：`tasks/service.py:425` 的 `load_project_membership` 换成 `require_project_action(..., action="run")`。
- 修「admin 进不去非成员项目」：`load_project_membership` 加 admin 旁路（返回 `(project, synthetic_member)` 或改为返回 `None` 并让调用方容忍）。**选后者风险更低**：新增 `load_project_for_user(db, *, project_id, user) -> Project | None`，`load_project_membership` 内部先调它，若 admin 则返回 `(project, None)`，调用方目前只用 `membership.role`，需 grep 确认 26 处里有几处直接用 role。
- **验收**：新增 `test/test_rbac_matrix.py`（每角色 × 每 action 的真值表，含 admin 旁路）；`test/test_project_task_acl.py` 全绿。

### 4.3 项目乐观锁
- 迁移加 `projects.version Integer NOT NULL DEFAULT 1`；`ProjectUpdate` 带 `expected_version`，`UPDATE ... WHERE id=? AND version=?`，`rowcount==0` → `ConflictException(currentVersion=...)`（复用 `candidate_set` 的既有实现范式）。
- **Files**：`models/projects.py`、`schemas/projects.py`、`api/v1/projects.py`、`services/project_access.py`、`services/rbac.py`（新）、`services/tasks/service.py`、迁移 1 个、测试 2 个。

---

## §5 Task 3：产物真值化（`refactor/artifact-as-truth`）

分 5 个 commit，每步独立可验证、可回滚。

### 5.1 `ArtifactVersion` 补 source
- 迁移 `20261030_04_artifact_version_source.py`：加 `source_task_id String(36) NULL`、`source_attempt_id String(64) NULL`、`source_tool_version_id String(36) NULL`、`storage_tier String(16) NOT NULL DEFAULT 'standard'`；索引 `(source_task_id)`、`(artifact_id, sha256)` 唯一（partial：`WHERE status='available'`）。存量行 source 为 NULL（合法：历史不可追）。
- 模型同步；`Artifact.source_task_id` 保留（兼容），但新写入同时写 Version 级。

### 5.2 引入 `ArtifactWriter`
- 新建 `backend/app/services/artifact_writer.py`：
  ```python
  @dataclass(frozen=True)
  class ArtifactSource:
      task_id: str; attempt_id: str | None; tool_version_id: str | None
  async def upsert_version(db, *, artifact, payload: ParsedStandardArtifact, source: ArtifactSource, storage) -> ArtifactVersion
  ```
  - 版本号：`SELECT version FROM artifacts WHERE id=:id FOR UPDATE` → `next = max+1`（SQLite 无 FOR UPDATE 时退化为 `BEGIN IMMEDIATE` 或捕获 `IntegrityError` 后重试 ≤3 次）。
  - 幂等：按 `(source.task_id, payload.ref, payload.sha256)` 查既有 Version，命中直接返回。
  - 一致性：`artifact_type = standard_type = semantic_type = ref_type`，写入前强校验三者可对齐（不允许上传路径自填 semantic_type）。
- `services/standard_artifacts.py` 改造为调用 `ArtifactWriter`；`services/artifacts.py` 的上传路径同样改为调用它（**保留旧函数签名**，内部转发）。

### 5.3 血缘自动写
- `ArtifactWriter` 在写完 Version 后，若 `source.task_id` 非空，则：
  1. 读 `task_input_snapshots`，把 `entity_type == "artifact_version"` 的行取 `entity_id`；
  2. 对每个输入 Version 写 `ArtifactLineage(input_version_id, output_version_id, relation_type="derived_from")`（`INSERT ... ON CONFLICT DO NOTHING`，靠 `uq_artifact_lineage_input_output` 幂等）。
- 保留 result.json `relations` 里声明的输出间边（两类边共存，`relation_type` 区分：`derived_from` / `declared_relation`）。
- **验收**：新增 `test/test_artifact_lineage_from_snapshot.py`——跑一个带输入的真实任务，断言产出物有指向输入 Version 的边。

### 5.4 单份存储 + 流式 + 预签名
- 上传路径去掉「先 `storage.upload` 再 `store_file_bytes`」的双写，只走 `store_file_bytes` 并让 `ArtifactVersion.storage_key` 指向同一个 `File.storage_path`。
- 下载端点改 `StreamingResponse`（按 1MB chunk 从 `StorageBackend` 流式读；`MinIOStorageBackend` 加 `open_stream(path)`）；`>100MB` 或 `.dcd/.xtc/.trr` 直接返回 15 分钟预签名 URL。
- 删除 `files/deduplication.py`（死代码）与 `File.reference_count`（只在死代码里维护）。

### 5.5 分页与校验前置
- `GET /projects/{id}/artifacts` 改 `paginated_response`；同步前端 `types/artifacts.ts`。
- 上传 API 复用 `validate_standard_artifact_roles`；`StandardArtifactRegistryError` 映射 422。

### 5.6 生命周期
- 新增 `services/artifact_gc.py`：按「`File` 无任何 `ArtifactVersionFile` 引用且超过 30 天」回收对象与行；项目删除改为先枚举 `ArtifactVersion.storage_key` 逐个 delete 再删行。
- 挂进现有 sweep 体系（带 Redis 选主锁）。

**不做**：`TaskOutput` 废弃（见 §1）。

---

## §6 Task 4：执行链路硬化（`fix/execution-hardening`）

1. **`blocked` 终结**：`workflow_scheduler.py:99-108` 的收口集合加 `blocked`；新增 `WORKFLOW_RUN_TIMEOUT_SECONDS`（默认 12h），在 `reconcile` 里把超时 run 置 `failure` + `error_message`；`workflow_cancellation` 的终止集合同步加 `blocked`。
2. **大产物流式**：`storage/minio_backend.py` 加 `open_stream`；`kubernetes_artifacts.py` 改「流式下载 → 流式算 sha256 → 流式上传」，峰值内存 = 1 个 chunk；`base.py:179-180` 的吞异常改为 `logger.exception` + 记录到 `error_message`。
3. **drp-runner 契约**：`deploy/model-images/*/platform_run_v2.sh` 加 `trap 'on_term' TERM`，`on_term` 里上传已产出物并 `exit 13`；注入 `DRP_TASK_FILE`/`DRP_RESULT_FILE`/`DRP_OUT_DIR`/`DRP_MODEL_ENTRY`/`DRP_DEVICE`/`DRP_HEARTBEAT_SEC`/`DRP_MAX_MINUTES`（与 `SCIMINER_*` 并存一个版本）；退出码映射 10/11/12/13。
4. **run 快照 tool_version**：`workflow_tool_scheduler.py:88` 建 run 时把 `tool_version_id` 写进节点状态，后续用快照而非实时 `current_version_id`。
5. **节点建任务幂等**：`workflow_task_lookup` 的去重键改 `(run_id, node_id, attempt)` 唯一索引，不再靠"最近 20 条"。

---

## §7 Task 5：资产统一（`feat/asset-unification`）

1. `Artifact` 作为资产根：`artifact_type` 受控枚举（`compound_set`/`protein_structure`/`binding_pocket`/`ligand_structure`/`molecule_table`/`md_trajectory`/`run_report`/`dataset`）。
2. P-12 数据资产页 Tab 改为 **化合物 / 蛋白 / 数据集**（按 `docs/06:67`），候选物归到 M3 域（保留页面，移出资产 Tab）。
3. `GET /projects/{id}/assets?type=` 统一检索，底层查 Artifact。

---

## §8 全局验收

- 后端全量 `pytest test/`：Windows 6 个已知差异外全绿；CI（Linux）应 0 失败。
- 前端 `vitest` 全绿 + `vue-tsc` 0 告警。
- `alembic heads` 单头且为 `20261030_05`（或实际最终号）；`upgrade head` / `downgrade base` 双向通过；真 PG 上跑一遍。
- `check_doc_links.py` / `check_offline_compliance.py` PASSED。
- 新增守护测试清单：`test_frontend_enum_parity`、`test_rbac_matrix`、`test_artifact_lineage_from_snapshot`、`test_artifact_writer_idempotent`、`test_blocked_node_terminates`、`test_large_artifact_streaming`。

---

## §9 Self-Review（写完后自查）

1. **Spec 覆盖**：docs/04 §5.0/§5.4/§5.6、§9；docs/05 §1.2/§9.2/§10.1；docs/06 P-12；docs/10 DB-09 —— 均有对应 Task。审计 §5.4 只做了「不丢」，**未做「登录/提交/重试补审计」**，这是刻意留给 Task 6（下一批），需在 §1 表中补一行说明。
2. **步骤可执行性**：每个 Task 都有文件清单 + 验收命令；迁移号已顺延；无「待定」项（角色改名、get_db、TaskOutput、多副本均已明确不做）。
3. **类型一致性**：`project_id_expression()` 保留签名、返回类型由表达式变 Column，已在 §4.1 标注 reviewer 关注点；`ArtifactSource` 字段与迁移列名一致。
4. **Review Focus**：已在头部列 6 条，覆盖迁移/静默降级/唯一约束/枚举一致/越权/信封。
5. **比例**：Task 3 占 8-10 天但价值最高；Task 1 只 2 天却立刻减痛，顺序正确。

## §10 实施结果

（各 PR 合入后回填）
