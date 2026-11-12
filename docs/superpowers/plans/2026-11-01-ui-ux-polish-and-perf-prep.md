# UI/UX 完善与平台压测准备（2026-11-01）

> 用户选择「先①」：先把**前端 UI/UX 做扎实**，同时**把压测的准备做到可执行**（压测本身在准备完成后按本计划执行）。
> 本计划只做「不改变业务语义」的体验与可观测性建设；不新增业务功能、不改接口契约、不改状态机。

## Goal

1. **UI/UX 完善**：以 `docs/02-架构/06-UI交互与原型说明.md` §1/§2/§3/§6/§7/§8/§9 为唯一验收口径，把 40 页里「已完成但不像成品」的地方收口到可对外演示、可交甲方的水平。
2. **压测准备**：形成可重复的压测资产（数据种子、场景脚本、环境编排、指标基线、通过标准），做到「一条命令起压测、一份报告看结论」。
3. 两条线都**不引入新依赖到生产运行时**（压测工具只进 dev/ops 依赖）。

## 现状证据（2026-11-01 勘查）

- 前端：`frontend/src/views` 下 62 个 `.vue`，`frontend/src/router/index.ts` 定义 59 条路由；UI 文档要求 40 页。
- 设计系统：`frontend/src/assets/styles/variables.less` 已 Dark-first、含 `@spacing-*`/`@font-size-*`/`@radius`/`@shadow-*` 与 `--theme-*` CSS 变量；`global.less`、`antd-override.less` 提供全局与 AntDV 覆写。
- 复用组件已存在：`frontend/src/components/common/` 下 `AppPageHeader.vue`、`AppEmptyState.vue`、`AppErrorState.vue`、`AppFilterBar.vue`、`SkeletonList.vue`、`SkeletonDetail.vue`、`SkeletonCard.vue`、`ProtectedAvatar.vue`、`CommandPalette.vue`。
- 现存不一致：`frontend/src/views` 内仍有 **49 处硬编码十六进制色值**（`#f0f0f0`×6、`#8c8c8c`×6、`#1677ff`×5、`#5b8ff9`×4、`#61ddaa`×3、`#595959`×3、`#52c41a`×3 等），暗/浅主题切换时会出现「一处变色、一处不变」。
- 可观测性：`backend/app/monitoring/prometheus_metrics.py`、`backend/app/monitoring/metrics_collector.py`、`backend/app/middleware/trace.py` 已存在；无 k6 可执行文件，无现成压测脚本。
- 数据库：本地 kind 内 `sciminer-postgres`（NodePort 30532）、`sciminer-redis`、`sciminer-storage`（MinIO NodePort 30900）；后端本地 uvicorn 运行于 8000，前端 vite 运行于 5173。
- 列表分页：结果中心 / 产物 / 工作流运行 / 任务 / 审计日志均已支持 keyset 游标（`backend/app/common/keyset.py`），压测应覆盖「深页」路径。

## 范围与非目标

**做**：视觉一致性、状态反馈（空/错/加载/禁用/危险操作）、关键页面动线与信息层级、响应式、可访问性、i18n、压测资产与基线。
**不做**：新增页面/业务功能、改后端 API 契约、改权限模型、改任务状态机、渲染级视觉大改版（保持 Dark 基调与现有布局）。

---

## 阶段 1｜视觉与设计系统收口（P0，2.5 天）

### 1.1 设计 token 单一真源

- `frontend/src/assets/styles/variables.less`：补/统一以下语义 token（已有则对齐命名）：
  - 表面：`@surface-base`（页面底）、`@surface-elevated`（卡片）、`@surface-sunken`（表格斑马/输入底）
  - 文本：`@text-primary` / `@text-secondary` / `@text-tertiary` / `@text-inverse`
  - 边框：`@border-base` / `@border-strong` / `@border-subtle`
  - 状态：`@success/warning/error/info`（已有），补对应 `*-bg` 弱底
  - 图表：`@chart-1..@chart-8`（供 ECharts 主题）
- `frontend/src/assets/styles/global.less`：把 `body`/滚动条/选中态/表格斑马纹/卡片阴影统一到上述 token；暗/浅主题必须在 `[data-theme="light"]` 下逐项有覆盖。
- 产出 `frontend/src/assets/styles/design-tokens.md`（一页速查：token → 用途 → 暗/浅值）。

### 1.2 清除视图层硬编码颜色

- 目标：`frontend/src/views/**/*.vue` 内十六进制色值 **49 → 0**（允许极少数第三方组件内联色，但必须注释原因）。
- 执行顺序：`grep -rnE '#[0-9a-fA-F]{6}' frontend/src/views` 逐文件替换为 token；图表色统一走 `@chart-*` 或 `frontend/src/utils/chartTheme.ts`（新建）。
- 验收：`grep` 仅剩注释/白名单；暗/浅截图逐页对照无色差断层。

### 1.3 卡片/表格/表单密度统一

- 卡片：圆角 8px、内边距 `@spacing-lg`、标题 16px/600、次级信息 13px `@text-secondary`。
- 表格：默认中等密度、13px、数字列右对齐且 `font-variant-numeric: tabular-nums`；操作列固定右侧。
- 表单：标签右对齐或上置统一（按 docs/06 §8），必填星号、单位后缀、帮助文案统一。
- 落点：`antd-override.less` 统一覆写；视图层不再各写局部 `:deep(.ant-table...)`。

### 1.4 侧边栏与全局框架

- `frontend/src/components/layout/AppShell.vue`：分组标题 12px/大写/字距、当前项左侧 3px 强调条；折叠态 tooltip；移动端抽屉。
- 顶部：面包屑/页面标题/全局搜索（CommandPalette 入口）对齐；`AppPageHeader.vue` 统一标题+描述+主操作区。

**阶段 1 验收**：`vue-tsc -b` 0；`grep` 硬编码色 0；暗/浅主题各 10 个代表页截图通过人工对照；无布局抖动。

---

## 阶段 2｜交互与状态一致性（P0，2 天）

### 2.1 列表页统一「四态」

每个列表页（项目/任务/结果/产物/用户/审计/模型/工作流）必须齐备：

| 状态 | 组件 | 要求 |
|---|---|---|
| 加载 | `SkeletonList.vue` | 首屏骨架 ≥ 3 行；翻页只按钮 loading，不整页闪 |
| 空 | `AppEmptyState.vue` | 说明用途 + 一键开始（跳转新建/导入） |
| 错误 | `AppErrorState.vue` | 现象 + 原因 + 重试按钮；网络错误自动重试 1 次 |
| 有数据 | 表格/卡片 | 分页/加载更多、总数、排序、筛选回显 |

- 盘点命令：`grep -rL "AppEmptyState" frontend/src/views/**/List.vue`，逐页补齐。
- 翻页统一复用 `frontend/src/utils/pagination.api.ts` 与「加载更多」；不允许整页 reload。

### 2.2 详情/任务页统一「过程可见」

- 任务详情 `frontend/src/views/tasks/Detail.vue`：状态时间轴（排队→运行→成功/失败）、阶段与百分比、日志自动滚动+暂停、产物卡片、失败「哪里错+怎么办」。
- 长任务（>30s）一律异步化提示；>10min 提示去任务中心，不在页面转圈（docs/06 §6.2）。
- 所有提交按钮：提交中 loading + 防重复点击；危险操作（删除/取消长任务）二次确认。

### 2.3 表单与校验

- Schema 驱动表单（`frontend/src/components/tasks/ParamSchemaForm.vue` 或等价）：必填、单位、默认值、范围提示；错误定位到字段。
- 文件上传：格式/大小前置校验，错误文案按 docs/06 §7 模板（现象+原因+下一步）。
- 统一 `useFormDirtyGuard`：有未保存修改离开时确认（新建/编辑页）。

### 2.4 可访问性与 i18n

- 可交互元素 `aria-label`/`role`；键盘可达（Tab 顺序、Esc 关弹窗、Enter 提交）；焦点可见。
- 颜色对比度 ≥ WCAG AA（正文 4.5:1、大字 3:1）。
- 所有新增文案进 `frontend/src/locales/{zh-CN,en-US}/index.ts`；禁止视图内硬编码中文（现有存量逐步收口，新增零硬编码）。

**阶段 2 验收**：8 个列表页四态齐全；任务详情过程可见；`vitest` 相关组件测试通过；Playwright 冒烟 12 条关键动线通过。

---

## 阶段 3｜关键页面视觉走查与打磨（P1，2 天）

按用户旅程逐页走查（不做功能改造，只调层级/留白/对齐/文案）：

1. 工作台 `views/home/index.vue`：首屏信息密度、项目卡、进行中任务、最近结果。
2. 项目总览 `views/projects/Overview.vue`：统计卡口径、进行中任务、成员。
3. 靶点/结构 `views/targets/*`、`views/structures/*`：3D 懒加载、pLDDT 图例、口袋表。
4. 提交类 `views/tasks/Create*.vue`、`views/design/*`、`views/predict/*`、`views/screen/*`：参数表单、算力预估单（XL 阻断）、提交反馈。
5. 结果类 `views/results/*`、`views/tasks/Result*.vue`：指标矩阵、筛选排序、导出、3D 联动。
6. 管理台 `views/admin/*`：模型/工具、算力队列、用户、审计。
7. 认证 `views/auth/Login.vue`：错误可执行、记住我、品牌区。

每页产出「改前/改后」截图，存 `docs/evidence/ui-ux-2026-11/`；发现的功能缺陷只登记到 `docs/18` §8，不在本阶段顺手改业务逻辑。

---

## 阶段 4｜压测准备（P0，2 天）

### 4.1 压测目标与 SLO（先定口径，再压）

以「企业内部 50–200 人并发、日任务 500–2000」为设计负载，建议 SLO（待用户确认后固化）：

| 指标 | 目标 |
|---|---|
| 读接口 P95 | ≤ 300ms（列表首屏）、≤ 150ms（详情） |
| 写接口 P95 | ≤ 800ms（提交任务）、≤ 1s（上传元数据） |
| 错误率 | < 0.5%（不含 4xx 业务拒绝） |
| 深页列表 | 第 1 页 vs 第 5000 页 P95 差异 ≤ 2× |
| 任务提交→入队 | P95 ≤ 2s；队列积压可见 |

### 4.2 压测资产（新增目录 `perf/`）

- `perf/k6/`（首选，需下载 k6 单文件二进制放 `perf/bin/`，不入库）：
  - `smoke.js`（1 VU 走通登录→项目→结果→任务详情）
  - `read.js`（列表/详情读，阶梯 10→50→100 VU，含深页 cursor）
  - `write.js`（创建项目/提交任务/上传小文件，含幂等键）
  - `mixed.js`（70% 读 30% 写，soak 30–60min）
  - `lib/auth.js`、`lib/data.js`、`lib/thresholds.js`
- 兼容方案（离线优先）：若无法取得 k6，则 `perf/locustfile.py`（locust）或 `scripts/perf_load.py`（httpx + asyncio，仓库已依赖 httpx），输出同样的 JSON 指标。
- `perf/README.md`：一条命令起环境、造数、跑场景、出报告。

### 4.3 数据种子（`scripts/perf_seed.py`）

- 可参数化：项目数、每项目任务数、产物数、用户数；默认 20 项目 × 5000 任务 = 10 万任务、20 万产物。
- 直连 PG（`DATABASE_URL`）批量 `COPY`/`executemany`，幂等（按 prefix 清理）。
- 必须造出：终态/运行中混合、同毫秒 `finished_at` 至少 5 行（验证 keyset 不重不漏）、长列表深页。

### 4.4 环境与观测

- 后端固定 `uvicorn --workers 4`（与生产一致）；PG/Redis/MinIO 用 kind 内中间件；记录 CPU/内存/连接数。
- 指标来源：`/metrics`（Prometheus 文本）、`middleware/trace.py` 的 trace 头、PG `pg_stat_statements`（若开启）、uvicorn access log 抽样。
- 采集脚本 `perf/collect.sh`：压测前后各抓一次 `EXPLAIN (ANALYZE, BUFFERS)` 关键查询（结果/产物/任务/workflow 列表）。

### 4.5 执行与报告

- 阶梯：smoke(1 VU) → baseline(10 VU) → load(50 VU) → stress(100/200 VU) → soak(30min@50 VU)。
- 每轮产出 `perf/results/<timestamp>/summary.json` + `report.md`：吞吐、P50/P95/P99、错误率、DB 慢查询 Top10、瓶颈判断（CPU/锁/连接池/网络）。
- 通过标准：达到 4.1 SLO 且无内存持续增长、无连接池耗尽、深页无 `TEMP B-TREE`。

**阶段 4 验收**：`perf/README.md` 按步骤可复现；smoke 与 baseline 两轮实跑通过；瓶颈清单进入 `docs/18` §8 待办。

---

## 交付物

- 代码：设计 token/主题、组件统一、关键页走查改动、`perf/` 全套脚本、`scripts/perf_seed.py`。
- 文档：`docs/superpowers/plans/2026-11-01-ui-ux-polish-and-perf-prep.md`（本文件）；压测报告 `perf/results/<ts>/report.md`；`docs/18` 追加 §UI/UX 与性能章；`docs/06` 若发现规范缺口则回写。
- 证据：`docs/evidence/ui-ux-2026-11/` 每页改前/改后截图；压测 summary。

## Global Constraints

- 不改后端 API 契约/返回字段（只允许前端展示层变化）；不改权限与状态机。
- 全部既有测试继续通过：`pytest`（2080+，已知 3 个 Windows 环境用例除外）、`vitest`、`vue-tsc -b`；`flake8 F401,F821,E9` 零输出。
- 不新增生产运行时前端依赖；压测工具仅进 `perf/`（不入 `package.json` 生产依赖）。
- 迁移不涉及（本计划不动数据库结构）；若压测脚本需要索引，走独立迁移并保持单 head。
- 中文/英文文案同步；不引入外部 CDN/字体（离线部署约束 C-1）。

## Sequencing

1. 阶段 1（token + 硬编码清零 + 密度）→ 我与前端子智能体并行，先落地再走查。
2. 阶段 2（四态 + 任务过程 + 表单）→ 前端子智能体执行，我审查。
3. 阶段 3（走查打磨）→ 我主导截图走查，子智能体改细节。
4. 阶段 4（压测准备）→ 后端子智能体写脚本，我在本地 kind 环境实跑 smoke/baseline。
5. 全部收口后更新文档并提交（按 `feat(web)` / `test(perf)` / `docs` 拆分）。

## Risks

- **视觉改动面大**：以 token 化 + 截图对照控制回归；每阶段独立提交，可回滚。
- **压测环境与生产不一致**：本地 kind 单节点，结论只用于容量趋势与瓶颈定位，不当作生产 SLA。
- **k6 获取**：内网可能无法下载；已备 locust/httpx 方案。
- **既有测试基线**：3 个 Windows 环境失败为已知项，不因本计划新增失败。

## Review Focus

1. 硬编码色是否真正清零（`grep` 证据），暗/浅主题是否每页成立。
2. 列表四态是否每页齐备，空状态是否「引导型」而非一句「暂无数据」。
3. 任务详情是否满足 docs/06 §6 的「等待可见」与「错误可执行」。
4. 压测是否覆盖深页游标、写接口幂等、混合负载与 soak；SLO 是否可量化对比。
5. 全程不改 API 契约、不改权限/状态机、测试基线不退化。

## Status（2026-11-01）

- 阶段 1（设计 token/暗亮双主题/视觉）：完成。
- 阶段 2（9 页四态 + AppInlineError）：完成。
- 阶段 3（40 路由走查 + P1/P2 修复）：完成；证据 `docs/evidence/ui-ux-2026-11/`。
- 阶段 4（压测准备）：脚本 `perf/`、`scripts/perf_seed.py`、`scripts/perf_load.py` 已就位；
  baseline 实跑与容量报告留待下一阶段。
