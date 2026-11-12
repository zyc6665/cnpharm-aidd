# 关键页面视觉走查报告（阶段3）

- 仓库：`D:\workbuddy\中国医药平台项目\_upstream_CPUmodel_V2`
- 前端：http://127.0.0.1:5173 （dev server，未重启、未改动）
- 后端：http://127.0.0.1:8000
- 走查时间：2026-11-01 09:05–09:20（Asia/Shanghai）
- 视口：桌面 1440×1000、移动 390×844，整页截图（fullPage）
- 主题：`data-theme="dark"`（平台默认暗色）+ `colorScheme: dark`，语言 zh-CN
- 登录：`admin` / 口令由 `backend/.tmp_mw.env` 的 `ADMIN_PASSWORD` 注入（未落盘、未打印）
- 账号数据：项目 1 个（默认项目 `9dc916fa…`）、任务 9 个（全部 success）、工具 9 个、工作流 0、靶点/结构/口袋/候选物/候选集均为 0
- 截图根目录：`docs/evidence/ui-ux-2026-11/{desktop,mobile}/`
- 原始数据：`docs/evidence/ui-ux-2026-11/walkthrough-data.json`（每页 URL/控制台/失败请求/交互结果）

**结论速览**：共走查 40 条路由 × 2 端 = 80 张整页截图，另 19 张交互截图；页面级控制台/HTTP 错误仅 2 类（任务详情 SSE 双前缀 404——走查后 09:17 已修复并复核通过、预测结果表格 `rowKey` 警告），无 5xx。视觉问题集中在移动端：表格右侧列被裁切、项目总览统计卡单列堆叠、项目导航/管理 Tab 横向裁切。交互主流程（登录校验、项目卡→总览、任务卡→详情、结果空态、新建用户弹窗）均可用。

---

## 1. 覆盖总表

> 「控制台/HTTP」仅记录该页真实产生的错误/失败请求；空态属数据现状，不算错误。

| 编号 | 页面 | 路由 | 桌面截图 | 移动截图 | 控制台 / HTTP 错误 | 主要视觉问题（严重度） |
|---|---|---|---|---|---|---|
| P-01 | 登录 | `/login` | `desktop/login.png` | `mobile/login.png` | 无 | 无（布局正常） |
| P-02 | 工作台首页 | `/`（重定向 `/workspace`） | `desktop/home.png` | `mobile/home.png` | 无 | 文档写 `/home`，实际 `/` 重定向 `/workspace`（P3，信息架构） |
| — | 工作台（研究项目） | `/workspace` | `desktop/workspace.png` | `mobile/workspace.png` | 无 | 移动端项目行操作链接「项目总览/归档/删除」换行错位；「待审批与失败任务」空态占位过高（P3） |
| P-03 | 项目列表 | `/projects` | `desktop/projects.png`（404） | `mobile/projects.png`（404） | 路由未注册 → 404 | **路由缺失**：`/projects` 落到 404，项目列表能力实际由 `/workspace` 承担（P2） |
| P-04 | 项目总览 | `/projects/:id` | `desktop/project-overview.png` | `mobile/project-overview.png` | 无 | 移动端 8 张统计卡单列堆叠，页面高 3250px；全 0 指标视觉噪声大（P2） |
| P-06 | 靶点列表 | `/projects/:id/targets` | `desktop/project-targets.png` | `mobile/project-targets.png` | 无 | 空态（0 靶点），卡片栅格正常（P3：空态留白偏多） |
| P-33（项目内） | 结果中心 | `/projects/:id/results` | `desktop/project-results.png` | `mobile/project-results.png` | 无 | 移动端表格右侧「状态/完成时间/提交人/耗时」被裁切且无横向滚动提示；桌面「类型」列换行（P2/P3） |
| — | 候选物 | `/projects/:id/candidates` | `desktop/project-candidates.png` | `mobile/project-candidates.png` | 无 | 空态正常（0 候选物） |
| P-39 | 决策记录 | `/projects/:id/decisions` | `desktop/project-decisions.png` | `mobile/project-decisions.png` | 无 | 空态正常 |
| P-12 | 数据资产 | `/projects/:id/assets` | `desktop/project-assets.png` | `mobile/project-assets.png` | 无 | 空态正常（0 化合物）；移动端「批量导入/新增化合物」按钮换行（P3） |
| — | Artifact 谱系 | `/projects/:id/lineage` | `desktop/project-lineage.png` | `mobile/project-lineage.png` | 无 | 节点图在移动端偏小（P3） |
| — | 项目工作流 | `/projects/:id/workflow` | `desktop/project-workflow.png` | `mobile/project-workflow.png` | 无 | 空态正常 |
| — | 项目设置 | `/projects/:id/settings` | `desktop/project-settings.png` | `mobile/project-settings.png` | 无 | 正常 |
| P-05 | 项目成员 | `/projects/:id/members` | `desktop/project-members.png`（404） | `mobile/project-members.png`（404） | 路由未注册 → 404 | **路由缺失**（P2） |
| P-33 | 结果中心（全局） | `/results` | `desktop/results.png`（404） | `mobile/results.png`（404） | 路由未注册 → 404 | **路由缺失**：无全局结果路由，仅有 `/results/:taskId` 与 `/projects/:id/results`（P2） |
| P-34 | 结果详情 | `/results/:id` | `desktop/result-detail.png` | `mobile/result-detail.png` | 无 | 正常（长页、图表较多） |
| P-31 | 任务中心 | `/tasks` | `desktop/tasks.png` | `mobile/tasks.png` | 无 | 卡片「项目」显示项目 ID 前 8 位 `9dc916fa` 而非项目名；移动端 Tab 横向裁切（P2/P3） |
| P-32 | 任务详情 | `/tasks/:id` | `desktop/task-detail.png` | `mobile/task-detail.png` | **404 `/api/v1/api/v1/tasks/:id/events`** | SSE 事件流 URL 重复前缀；「输出结果」原始 JSON 树与暗色主题冲突（P1/P2） |
| P-17 | 生成结果 | `/tasks/:id/results` | `desktop/task-results.png` | `mobile/task-results.png` | 无 | 结果网格正常；移动端卡片偏高（P3） |
| P-22 | 预测结果 | `/tasks/:id/predictions` | `desktop/task-predictions.png` | `mobile/task-predictions.png` | 控制台警告：Table `rowKey` index deprecated | 移动端「指标矩阵」只露 SMILES 列、SMILES 串溢出裁切；页面高 **12,712px（≈15 屏）**，逐指标直方图纵向堆叠无折叠（P2） |
| P-24 | 筛选结果 | `/tasks/:id/screening` | `desktop/task-screening.png` | `mobile/task-screening.png` | 无 | 空态「没有找到筛选结果表」，功能未产出数据（P3 空态留白） |
| P-27 | MD 结果 | `/tasks/:id/md` | `desktop/task-md.png` | `mobile/task-md.png` | 无 | 移动端顶部指标卡标签逐字换行（「任务状态」「力场」「总步数」竖排）；页宽 398>390 横向溢出（P2/P3） |
| P-28 | 自由能结果 | `/tasks/:id/free-energy` | `desktop/task-free-energy.png` | `mobile/task-free-energy.png` | 无 | 正常 |
| — | 工具库 | `/tools` | `desktop/tools.png` | `mobile/tools.png` | 无 | 工具卡标题/描述截断无 tooltip；搜索需回车才生效（P3） |
| — | 工具详情 | `/tools/:id` | `desktop/tool-detail.png` | `mobile/tool-detail.png` | 无 | 正常 |
| P-29 | 工作流模板 | `/workflows/templates` | `desktop/workflows-templates.png`（404） | `mobile/workflows-templates.png`（404） | 路由未注册 → 404 | **路由缺失**：实际入口为 `/workflow`（工具工作台）（P2） |
| P-29（实际） | 工具工作台 | `/workflow` | `desktop/workflow.png` | `mobile/workflow.png` | 无 | 正常 |
| P-30 | 工作流实例 | `/workflows/:id` | `desktop/workflow-instance.png`（404） | `mobile/workflow-instance.png`（404） | 路由未注册 → 404 | **路由缺失**：实际为 `/workflow/runs/:runId`（P2） |
| P-15 | 分子生成 | `/design/molecules` | `desktop/design-molecules.png` | `mobile/design-molecules.png` | 无 | 页面提示「未找到分子生成工具(std-diff-molecule-generation)」，提交按钮禁用（P3，工具未发布） |
| P-16 | 多肽设计 | `/design/peptides` | `desktop/design-peptides.png` | `mobile/design-peptides.png` | 无 | 正常 |
| P-21 | 性质预测提交 | `/predict` | `desktop/predict.png` | `mobile/predict.png` | 无 | 必填未满足时「提交预测任务」仍可点击，仅事后报错（P2） |
| P-23 | 虚拟筛选配置 | `/screen` | `desktop/screen.png` | `mobile/screen.png` | 无 | 同上：提交按钮不禁用（P2） |
| P-26 | MD 提交 | `/md` | `desktop/md.png` | `mobile/md.png` | 无 | 正常（提交按钮正确禁用） |
| P-35（实际） | 工具管理 | `/admin/tools` | `desktop/admin-tools.png` | `mobile/admin-tools.png` | 无 | 文档 P-35 写 `/admin/models`，实际无该路由，由 `/admin/tools` 承担（P3） |
| P-36 | 算力队列 | `/admin/compute` | `desktop/admin-compute.png` | `mobile/admin-compute.png` | 无 | 「按厂商分布」空态大片留白（P3） |
| P-37 | 用户与权限 | `/admin/users` | `desktop/admin-users.png` | `mobile/admin-users.png` | 无 | 桌面「操作」列 4 按钮换行拥挤；移动端表格右侧列被裁切（P2/P3） |
| P-38 | 审计日志 | `/admin/audit` | `desktop/admin-audit.png` | `mobile/admin-audit.png` | 无 | 桌面行高密、RequestID 换行；移动端表格裁切（P3） |
| — | 项目成果展示 | `/achievements` | `desktop/achievements.png` | `mobile/achievements.png` | 无 | 正常 |
| — | 个人资料 | `/user` | `desktop/user.png` | `mobile/user.png` | 无 | 正常 |
| — | 404 | `/404` | `desktop/not-found.png` | `mobile/not-found.png` | 无 | 正常 |

---

## 2. Top 10 待修问题

### 1）【P1·走查时复现，09:17 已修复】任务详情实时事件流 URL 重复 `/api/v1`，SSE 404
- 现象（走查时）：进入任务详情，`GET /api/v1/api/v1/tasks/{id}/events` 返回 404；浏览器控制台报 `Failed to load resource: 404`。实时状态/进度/日志推送失效，只靠 5s 轮询兜底。
- 复现：登录 → `/tasks/41156b31-98d2-40fe-b5c7-cd38fca33321` → 看 Network。桌面与移动端均复现（`desktop/task-detail.png`、`mobile/task-detail.png`）。
- 原因：`frontend/.env.development` 的 `VITE_API_BASE_URL=/api/v1`，而代码又拼了一次 `/api/v1`。
- 当前状态（09:17 修复 / 09:20 复核）：主代理已修改 `frontend/src/api/task-events.ts:74-77` 为 `const prefix = base || '/api/v1'; return `${prefix}/tasks/${taskId}/events``；再次打开同一任务详情页，`response.status>=400` 采集为空，**404 已消失，本 P1 关闭**（截图仍保留修复前证据）。
- 严重度：P1（走查时），修复后关闭

### 2）【P2】全局任务中心「项目」列显示项目 ID 片段而非项目名
- 现象：`/tasks` 每张任务卡显示「项目：9dc916fa Artifact 谱系」，应为「项目：默认项目」。
- 复现：`/tasks` → 任意任务卡底部项目行（`desktop/tasks.png`、`mobile/tasks.png`）。
- 原因：全局任务页无 `currentProjectId/currentProjectName` 上下文，`getTaskProjectContextLabel` 退回 ID 前 8 位。
- 建议改：`frontend/src/domain/tasks/navigation.ts:16` 的兜底分支；根治需任务列表接口返回 `project_name`（或前端按 `project_id` 查项目）；调用点 `frontend/src/components/tasks/TaskListCard.vue:179-182`。
- 严重度：P2

### 3）【P2】移动端项目总览：8 张统计卡单列堆叠，页面高达 3250px
- 现象：390px 下「靶点/结构/口袋/候选物/候选集/Artifact/任务/工作流」8 张卡各占满一整行，且多数为 0，纵向滚动很长。
- 复现：`/projects/:id` 移动视口（`mobile/project-overview.png`，390×3250）。
- 原因：`frontend/src/views/projects/Overview.vue:497-500` 在 `@media (max-width: @screen-md)` 把 `.overview-stats` 置为 `grid-template-columns: 1fr`。
- 建议改：移动端改 `repeat(2, minmax(0,1fr))`（`Overview.vue:492-501` 的媒体查询内），仅 `.overview-grid` 保持单列。
- 严重度：P2

### 4）【P2】移动端宽表格右侧列被裁切，且无横向滚动提示
- 现象：结果中心、用户管理、审计日志、预测结果「指标矩阵」在 390px 下只露出左侧 1–2 列，右侧列被硬裁切，界面无渐变遮罩/滚动条，用户不知道可横滑；预测结果页因此被撑到 **12,712px** 高（逐指标直方图纵向堆叠）。
- 复现：`mobile/project-results.png`（状态/完成时间/提交人/耗时不可见）、`mobile/admin-users.png`（「用户名」列被切半）、`mobile/admin-audit.png`、`mobile/task-predictions.png`（仅露 SMILES 列）。
- 相关代码：`frontend/src/views/results/List.vue:57`（`:scroll="{ x: 'max-content' }"`）、`frontend/src/views/admin/Users.vue:101`、`frontend/src/views/admin/Audit.vue:103`、`frontend/src/views/predict/PropertyPredictResult.vue`（指标矩阵表）。
- 建议：移动端（≤768px）改为卡片/键值列表，或为表格容器加 `.table-scroll-hint`（右侧渐隐 + 「左右滑动查看更多」提示），并隐藏非关键列；预测结果页把「指标矩阵」与「分布直方图」改为 Tab 分栏。
- 严重度：P2

### 5）【P2】提交类页面必填校验前置不一致：按钮该禁用却可点
- 现象：`/predict`、`/screen` 在未上传文件/未选受体时，「提交」按钮仍为可用态，点击后才出现「请先上传 SMILES CSV 或选择候选集」「请上传受体结构」；而 `/md`、`/design/molecules` 按钮正确 `disabled`。
- 复现：`desktop/interaction-predict-submit-empty.png`、`desktop/interaction-screen-submit-empty.png`；实测 `disabledBefore=false`（md/design 为 true）。
- 相关代码：`frontend/src/views/predict/PropertyPredictSubmit.vue:85-98`（校验只在 `handleSubmit` 内做，按钮未绑定 `:disabled`）；`frontend/src/views/screening/ScreenConfig.vue` 提交按钮同理。
- 建议：按钮 `:disabled="!canSubmit"`（与 md 页一致），并保留行内校验文案。
- 严重度：P2

### 6）【P2】任务详情「输出结果」直接渲染原始 JSON 树，暗色下对比度差
- 现象：「输出结果」区块是 Result Viewer 的裸 JSON 树，嵌套浅灰面板配浅色文字，层级靠边框堆叠，超长（页面高 4240px），关键指标（Binding Energy 等）淹没在 `path/sha256/size` 字段里。
- 复现：`/tasks/:id` 向下滚动（`desktop/task-detail.png`）。
- 建议改：`frontend/src/views/tasks/Detail.vue` 输出区（Artifact 卡片渲染）为「摘要字段 + 折叠原始 JSON」，并统一暗色 token（背景用 `@bg-elevated`，文本 `@text-secondary`）。
- 严重度：P2

### 7）【P2】文档路由与实际路由不一致，5 个文档页面直接 404
- `/projects`（P-03）、`/projects/:id/members`（P-05）、`/results`（P-33）、`/workflows/templates`（P-29）、`/workflows/:id`（P-30）、`/workflows/templates/:id/edit`（P-40）均未注册，落到 `/404`（截图 `desktop/projects.png`、`desktop/project-members.png`、`desktop/results.png`、`desktop/workflows-templates.png`、`desktop/workflow-instance.png`）。
- 影响：按文档走查/验收/外部链接会直接 404；用户从书签进入失败。
- 建议：`frontend/src/router/index.ts` 增补别名或 302 到实际实现（`/projects`→`/workspace`，`/results`→ 项目内结果中心，`/workflows/*`→`/workflow`），或修订 `docs/02-架构/06-UI交互与原型说明.md` §3 路由列。
- 严重度：P2（若产品确认按文档交付则为 P1）

### 8）【P2】移动端项目导航 / 管理台 Tab 横向裁切，无滚动提示
- 现象：390px 下项目二级导航（项目总览/靶点与结构/Workflow/任务中心/数据资产…）与后台 Tab（仪表盘/用户管理/工具管理…）在右边缘被直接切断，无渐隐或箭头。
- 复现：`mobile/project-overview.png`、`mobile/admin-users.png`、`mobile/admin-audit.png`。
- 相关代码：`frontend/src/components/projects/ProjectWorkspaceNav.vue:46-53`（`overflow-x:auto` 已可滑，但无可见提示；WebKit 默认隐藏滚动条）。
- 建议：加右侧渐隐遮罩与「滑动查看更多」提示，或在移动端收进「更多」下拉。
- 严重度：P2（可用性）

### 9）【P3】工作台移动端项目行操作链接换行错位 / 空态占位过高
- 现象：项目行右侧「项目总览 归档」在一行、「删除」掉到下一行且贴右，视觉断裂；「待审批与失败任务」空态固定高度约 300px，移动端大片空白。
- 复现：`mobile/workspace.png`。
- 建议改：`frontend/src/views/workspace/index.vue` 项目行操作区在小屏改为 `flex-wrap: wrap; justify-content: flex-end` 或折叠进「…」菜单；空态 `min-height` 在 ≤768px 降至 160px。
- 严重度：P3

### 10）【P3】零散视觉细节
- 结果中心桌面「类型」列宽不足，工具名换两行（`desktop/project-results.png`），建议列宽 ≥220 或 `white-space: nowrap` + tooltip。
- 用户管理桌面「操作」列 4 个链接按钮纵向换行、行高被撑到 ~90px（`admin/Users.vue:403-411` 列宽 260），建议收进「更多」下拉。
- 工作流/算力空态卡片留白过大（`desktop/admin-compute.png`）。
- 项目总览 8 个统计卡大量为 0，建议零值弱化或合并次要指标。
- 移动端 MD 结果顶部指标卡标签逐字竖排（`mobile/task-md.png`：任务状态/力场/总步数/模拟时长/时间步长），需给标签 `white-space: nowrap` 或改为单列布局。
- `mobile/project-overview.png` 实际宽 398px、`mobile/task-md.png` 398px > 390，存在 8px 横向溢出（需补 `overflow-x:hidden` 或修 `min-width`）。

---

## 3. 交互抽查结果（桌面）

| 交互 | 结果 | 证据 |
|---|---|---|
| 登录空表单提交 | ✅ 出现 2 条行内校验错误（账号/密码必填） | `desktop/interaction-login-empty.png` |
| 错误密码登录 | ✅ 提示「用户名或密码错误」，输入框可继续编辑 | `desktop/interaction-login-wrong.png` |
| 工作台项目卡点击 | ✅ 跳转 `/projects/9dc916fa…` 项目总览 | `desktop/interaction-workspace-project-click.png` |
| 任务行点击 | ✅ 跳转 `/tasks/41156b31…` 任务详情 | `desktop/interaction-tasks-row-click.png` |
| 任务列表状态筛选 | ✅ 下拉可选并刷新列表（全部为 success，视觉无变化） | `desktop/interaction-tasks-status-filter.png` |
| 结果列表空态 | ✅ 选「失败」→「共 0 条」+「项目内还没有已完成的结果」+ 清除筛选 | `desktop/interaction-results-empty.png` |
| 工具搜索 | ⚠️ 输入 `a` 后卡片数仍为 9（9→9）；`a-input-search` 仅回车/点图标触发，无即时过滤，易被误认为失效 | `desktop/interaction-tools-search.png` |
| 工具卡点击 | ✅ 跳转 `/tools/:id` 工具详情页（非抽屉/弹窗） | `desktop/interaction-tool-detail.png` |
| 新建用户弹窗 | ✅ 弹窗正常打开，账号/邮箱/名称/认证源/密码/角色/状态字段齐全 | `desktop/interaction-admin-create-user.png` |
| 审计日志筛选 | ✅ 下拉可展开、应用后刷新（首项为「全部」，故 51 行不变） | `desktop/interaction-audit-filter-open.png`、`desktop/interaction-audit-filter-applied.png` |
| 提交页表单（predict/screen/md/design-molecules） | ✅ 表单可见；predict/screen 按钮不禁用、点击后报错；md/design 正确禁用并给出原因提示 | `desktop/interaction-*-form.png`、`desktop/interaction-*-submit-empty.png` |

---

## 4. 未覆盖页面及原因

| 编号 | 文档路由 | 状态 | 原因 |
|---|---|---|---|
| P-05 | `/projects/:id/members` | 未覆盖 | 路由未注册，访问落 404（截图已留证） |
| P-07 | `/targets/:id` | 未覆盖 | 项目靶点数为 0，取不到真实 target id；不伪造 |
| P-08 | `/proteins/:id/predict` | 未覆盖 | 无蛋白/靶点数据，无 id |
| P-09 | `/structures/:id` | 未覆盖 | 结构数为 0（overview counts.structures=0），无 structure id |
| P-10 | `/structures/:id/pockets` | 未覆盖 | 口袋数为 0，无 structure/pocket id |
| P-11 | `/pockets/:id/residues` | 未覆盖 | 无口袋数据 |
| P-13 | `/compounds/:id` | 未覆盖 | 无化合物数据 |
| P-14 | `/projects/:id/import` | 未覆盖 | 路由表无 import 页面 |
| P-18 | `/candidate-sets/:id` | 未覆盖 | 候选集数为 0 |
| P-19 | `/candidates/:id` | 未覆盖 | 候选物数为 0 |
| P-20 | `/candidates/compare`（实际 `/projects/:id/candidates/compare`） | 未覆盖 | 需要 ≥2 个候选物，当前 0 |
| P-25 | `/docking-results/:id` | 未覆盖 | 无对接结果记录 id（AutoDock 任务仅有产物，无 docking-result 实体） |
| P-30 | `/workflows/:id` | 未覆盖 | 路由未注册（404 已留证）；工作流数为 0，实际实例页为 `/workflow/runs/:runId` |
| P-40 | `/workflows/templates/:id/edit` | 未覆盖 | 路由未注册（404 已留证），且无模板数据 |
| P-03 / P-33 / P-29 | `/projects`、`/results`、`/workflows/templates` | 已截图（404） | 路由未注册；对应能力在实际路径 `/workspace`、`/projects/:id/results`、`/workflow` 已覆盖 |

> 说明：`/login` 采用**未登录**独立上下文截取；`/`（P-02 文档 `/home`）实际重定向到 `/workspace`，故 `home.png` 与 `workspace.png` 内容一致，属实现现状而非重复截错。

---

## 附录 A：控制台 / HTTP 明细

| 页面 | 类型 | 内容 |
|---|---|---|
| `/tasks/:id`（桌面+移动） | HTTP 404 | `GET /api/v1/api/v1/tasks/41156b31-98d2-40fe-b5c7-cd38fca33321/events`（SSE 双前缀）——**09:17 已修复，09:20 复核无 404** |
| `/tasks/:id`（桌面+移动） | console error | `Failed to load resource: the server responded with a status of 404 (Not Found)` |
| `/tasks/:id/predictions`（桌面+移动） | console warning | `[ant-design-vue: Table] \`index\` parameter of \`rowKey\` function is deprecated…` |
| 全站其余 40 页 | — | 无 console error、无 ≥400 响应（除上述） |

> 首轮拍摄曾因脚本连续请求触发后端 429（`/api/v1/users/me`、`/tools` 等），导致部分页面被踢回 `/login`；已加限速＋退避重拍，最终 80 张截图为 attempts=1 干净结果，429 属测试手法问题，**不计入产品缺陷**。
>
> **时间戳说明**：本轮截图基于 2026-11-01 09:05–09:15 的前端构建；此后主代理已修复 `task-events.ts` 的 SSE 双前缀（mtime 09:17），任务详情 404 应以最终构建复核。其余页面证据不受影响。

## 附录 B：非视觉 / 业务逻辑观察（单列，供主代理参考）

1. 任务详情事件流双 `/api/v1` 前缀（见 Top1）同时是功能缺陷：SSE 永久 404，实时更新退化为 5s 轮询。
2. `/design/molecules` 提示「未找到分子生成工具（std-diff-molecule-generation），请先在工具库发布该工具包」，提交按钮禁用——环境缺工具包，非 UI 缺陷。
3. `/predict`、`/screen` 空提交依赖后端/前端异常文案提示，按钮不禁用（见 Top5）。
4. 工具搜索需回车触发（`views/tools/List.vue:40 @search`），非即时过滤。
5. 文档 P-35 写 `/admin/models`，实际无此路由，由 `/admin/tools` 承担；P-02 写 `/home`，实际 `/`。建议同步文档与实现。

## 附录 C：复现与产物

- 走查脚本（临时，非产品代码）：`frontend/.tmp_walkthrough.mjs`
  - 运行：`cd frontend && set -a; . ../backend/.tmp_mw.env; set +a; ADMIN_PASSWORD="$ADMIN_PASSWORD" node .tmp_walkthrough.mjs`
  - 特性：真实 Playwright 登录（httpOnly Cookie）→ 40 路由 × 桌面/移动整页截图 → 采集 console/pageerror/≥400 请求 → 19 项交互截图 → 写 `walkthrough-data.json`；内置限速与 429 退避、登录失效自动重登。
- 产物：
  - `docs/evidence/ui-ux-2026-11/desktop/*.png`（40 页 + 19 交互）
  - `docs/evidence/ui-ux-2026-11/mobile/*.png`（40 页）
  - `docs/evidence/ui-ux-2026-11/walkthrough-data.json`
