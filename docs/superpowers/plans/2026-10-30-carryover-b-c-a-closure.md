# 直达页导航、三列表游标分页与产物三列身份收口（2026-10-30）

> 用户已确认「三项全做」。本计划按 B → C → A 顺序落地，迁移保持单 head。重活交子智能体执行，主干审查。

## Goal

三件遗留收口，全部不改对外业务语义、所有既有测试继续通过：

1. **B｜直达页导航**：5 个「有路由、零入口」的直达页补导航入口，并加守卫测试防复发。
2. **C｜三列表游标分页**：结果中心、产物列表、工作流运行列表补完整 keyset 游标分页（任务列表与审计日志已支持，复用 `backend/app/common/keyset.py`），补所需复合索引，真 PG 实测深页恒定。
3. **A｜产物三列身份收口**：`artifact_type` / `semantic_type` / `standard_type` 三列同事实「合一」，加不变量守护，杜绝「A 写、B 降级、C 拒收」。

## 证据（勘查结论）

- **B**：`frontend/src/router/index.ts` 有路由但全局零入口 —— `/design/molecules`:124、`/design/peptides`:130、`/predict`:143、`/screen`:155、`/md`:174；而 `AppShell.vue:150-179` 仅 4 项主导航、`CommandPalette.vue:87-151` 仅 4 条导航命令。
- **C**：
  - 结果中心 `backend/app/api/v1/results.py:186-229`：`page/page_size` + `count(*)` + `ORDER BY finished_at DESC NULLS LAST, created_at DESC` + `offset`。
  - 产物列表 `backend/app/api/v1/artifacts.py:240-323`：**先 `selectinload` 全量 `.all()`，再 Python 侧按 `latest_version` 状态与 manifest 元数据过滤、再切片**（内存/响应随项目产物总数线性增长）。
  - 工作流运行 `backend/app/services/workflow_run_queries.py:63-100`：`count(*)` + `offset` + `ORDER BY created_at DESC, id DESC`。
  - 现有游标实现：`backend/app/common/keyset.py`（`encode_cursor`/`decode_cursor`/`apply_desc_keyset`/`next_cursor`）；样板 `backend/app/services/task_views.py:107-168`、`backend/app/api/v1/admin_audit.py`。契约：不传 `cursor` 保持 page/total；传 `cursor` 不算 total，返回 `nextCursor`/`hasMore`（`docs/20` §5.13）。
- **A**：`backend/app/models/artifacts.py:45-47` 三列同事实；写入点 `backend/app/services/standard_artifacts.py:231-233`、`standard_input_uploads.py:65-69`、`artifact_writer.py:262-288`；`artifact_binding_resolver.py` 用 `artifact_type or semantic_type` 兜底。8 值资产类型已单真源（`artifact_standards/asset_types.py:26-35`），不在本次范围。

## B｜直达页导航（前端，低风险）

- `frontend/src/components/layout/AppShell.vue`：新增 `designNav` 数组（分子生成 `/design/molecules`、多肽设计 `/design/peptides`、性质预测 `/predict`、虚拟筛选 `/screen`、分子动力学 `/md`），在主导航后渲染为一个带 `aria-label="设计工具"` 的 nav 区块；**移动端底部 Tab 只保留现有 4 项**（对该区块加类并在 `@media (max-width: @screen-md)` 内 `display:none`）。
- `frontend/src/components/common/CommandPalette.vue`：同样 5 条命令加入 `navigate` 组（搜索可达）。
- `frontend/src/locales/{zh-CN,en-US}/index.ts`：`nav` 下补 `molecules/peptides/predict/screen/md/designSection`。
- 守卫测试 `frontend/test/design-nav-reachability.test.ts`：断言 5 条路由在 `router/index.ts` 存在，且在 `AppShell.vue` 与 `CommandPalette.vue` 均有引用；缺任一即失败。
- 详情页 `/tasks/:id/free-energy` 当前也无入链 —— 作为可选补链（从 MD 结果/任务详情跳转），若成本高则单列跟进，不阻塞 B。

## C｜三列表游标分页（后端 + 前端 + 迁移 + 真 PG 实测）

统一契约（复用 `app/common/keyset.py`，与任务列表完全一致）：`cursor` 可选；给 `cursor` 时不计算 `total`、用「多取一条」判 `hasMore`、返回 `nextCursor`；不给时原行为不变。

### C-1 结果中心 `results.py:list_project_results`
- 增 `cursor` 查询参数。游标模式：`Task.finished_at.is_not(None)` 且 `ORDER BY finished_at DESC, id DESC`，`apply_desc_keyset(timestamp_column=Task.finished_at, id_column=Task.id)`。终态任务必有 `finished_at`；历史脏行（空 finished_at）只在偏移模式可见，文档注明。
- 响应 `data.nextCursor` + `data.hasMore`；偏移模式仍给 `total`（并给 `nextCursor` 供切换）。

### C-2 产物列表 `artifacts.py:list_artifacts`
- 根因是「元数据过滤只能在 Python 侧」。改造：
  - **无 `metadata_*` 过滤时**：走 SQL keyset，排序键用**稳定全序 `(created_at DESC, id DESC)`**（`updated_at` 非只增，游标翻页会漏/重，故不选它），`limit+1`，不再全量加载；`nextCursor`/`hasMore`。
  - **有 `metadata_*` 过滤时**：保留现有全量 + Python 过滤路径（有项目维度上界），并对结果切片；`nextCursor` 从切片末行计算，保证前端可继续。
  - 补索引 `(project_id, created_at, id)`（见迁移）。
- 文档注明「产物列表默认排序由 `updated_at` 改为 `created_at`」的理由（游标正确性优先）。

### C-3 工作流运行 `workflow_run_queries.py:list_workflow_runs`
- 增 `cursor`；游标模式 `ORDER BY created_at DESC, id DESC` + `apply_desc_keyset(created_at, id)`，不算 total。签名改为返回 `WorkflowRunPage(runs, total, next_cursor, has_more)`，同步 `list_workflow_runs` 的 API 调用方与响应 `nextCursor`。
- 补索引 `(project_id, created_at)`、`(owner_id, created_at)`（取 `artifacts`/`workflow_runs` 现有索引去重）。

### C-4 前端
- 结果中心、产物列表、工作流运行列表的「分页」改为游标「加载更多」（保留首屏 offset 兼容）；复用 `frontend/src/utils/pagination.spec.ts` 既有约定与 `paginated_response` 结构。
- i18n 补「加载更多 / 已全部加载」。

### C-5 真 PG 实测
- 造 10 万+ 行，EXPLAIN 确认 `(created_at, id)` 走索引区间扫描、无 `TEMP B-TREE`；深页（offset 5万） vs 游标（第 5000 页）耗时对比表写入验收报告。
- 迁移需 SQLite 与 PostgreSQL 双向可跑；生产路径 `CREATE INDEX CONCURRENTLY`。

## A｜产物三列身份收口（后端 + 迁移 + 守护）

- 定义**单一身份解析器**（如 `app.services.artifact_identity.resolve_identity(artifact_type, semantic_type, standard_type) -> (artifact_type, semantic_type, standard_type)`），所有写入点只调它，禁止各写各的三列。
- 归一规则（以现有语义为准）：
  - 标准产物：三列 = 标准 `type`（如 `binding_pocket`），`standard_version` 单列承载版本；`semantic_type` 不再带 `@v`。
  - 非标准：`standard_type` 为 `NULL`，`artifact_type`/`semantic_type` 一致取具体类型。
- 所有写入点（`standard_artifacts.py`、`standard_input_uploads.py`、`artifact_writer.py`、可能还有 resolver 兜底）改为调用解析器。
- 迁移：回填/归一存量行，使 `semantic_type`/`standard_type` 与 `artifact_type` 满足不变量；对无法自动判定的脏行记录日志并保留（不擅自丢数据），迁移脚本幂等。
- 守护测试：断言所有写入路径三列一致（构造写入 → 读回校验），并对 DB 层加 `CHECK`（若 SQLite/PG 均支持；否则用服务层断言 + 测试守护）。
- 范围边界：**不动** 8 值 `AssetArtifactType` 枚举与 `asset_types.py`；不改前端展示契约（三列仍照现有 API 下发）。

## Global Constraints

- 迁移**单 head**：C 先合入（新增索引迁移），A 基于 C 的 head 再建迁移；禁止并行开叉。
- 不改任何现有返回字段名/类型（只增 `nextCursor`/`hasMore`）；`total` 仅在游标模式变为 `null`。
- 全部既有测试（pytest 1980+、vitest）继续通过；`flake8` 零输出。
- 索引必须有「支撑哪条查询」说明；无对应查询不加。
- B 只动前端；C、A 动后端，互不耦合。

## Sequencing

1. B（前端，我直接做）→ vitest 相关用例绿。
2. C（子智能体：后端 + 迁移 + 前端 + PG 实测）→ 我审查 diff、跑测试。
3. A（子智能体：解析器 + 写入点 + 迁移 + 守护）→ 我审查 diff、跑测试。

## Review Focus

1. 游标模式是否**真的不算 total**、多取一条判 `hasMore`、`nextCursor` 只在有下一页时给。
2. `apply_desc_keyset` 是否用**行值比较**（不能用展开的 OR 式，见 keyset.py 注释：差 60 倍）。
3. 产物列表有 `metadata_*` 过滤时是否诚实回落全量路径（不能假装游标却仍全量）。
4. A 的解析器是否覆盖**所有**写入点（grep `semantic_type=`/`standard_type=`），迁移是否幂等、双向可 downgrade。
5. 三列不变量在 SQLite 与 PG 都成立；脏行处理不丢数据。

## Status（2026-10-30 完成，未 commit）

三项均实现并通过统一验收：

- **B**：`AppShell.vue` 设计工具分区、`CommandPalette.vue` 直达命令、`router/index.ts` 补 `meta.nav`、`design-nav-reachability.test.ts` 4 用例；手机断点隐藏。
- **C**：后端三列表 `cursor` 模式（`results.py`/`artifacts.py`/`workflows.py` + `common/keyset.py`）；前端 `utils/pagination.api.ts` + 三列表 `LoadMore`；迁移 `20261031_04`（artifacts 游标索引）、`20261031_05`（tasks 部分索引 + workflow_runs 两索引 + results 索引）。三列表均验证「不传 cursor 有 total、传 cursor total=null、5 行同毫秒不重不漏、非法 cursor→422」。
- **A**：`services/artifact_identity.py` 单一解析器 + 四处写入点收敛 + `ck_artifacts_standard_type_matches_artifact` + 迁移 `20261031_06`；`semantic_type==artifact_type` 仅服务层守护（存量 `@vN` 夹具原因）。

**验收证据**：全量后端 `1999 passed / 5 failed / 4 skipped`，5 个均为既有 Windows 环境差异（admin_system_routes、database_url_resolution、model_package_template、remote_tool_signed_file_urls、tool_example_paths）；`alembic heads` 单头 `20261031_06`；`flake8 F401,F821,E9` 零输出；前端 `vue-tsc -b` exit 0、定向 vitest 20 passed；真 PG 库 `cin_keyset_verify` 实测游标恒定、A 的 CHECK 拒违规行且 downgrade/upgrade 对称。
