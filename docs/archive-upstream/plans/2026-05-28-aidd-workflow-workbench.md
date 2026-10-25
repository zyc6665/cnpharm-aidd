# AIDD 流程工作台 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新增一个前端本地持久化的 AIDD 流程工作台页面，在同一页面内串联五个固定步骤，保留每一步结果，并自动把上一步输出带入下一步。

**Architecture:** 采用“单页工作流工作台 + 配置驱动步骤映射 + 持久化 Pinia store”方案。后端仍然保持单任务模型，前端通过新的 `workflow` 目录、`workflow` store 和步骤配置层，把现有工具详情页与任务详情页能力编排成连续流程，不复用后台工具分类作为流程步骤。

**Tech Stack:** Vue 3、TypeScript、Pinia、pinia-plugin-persistedstate、Vue Router、Ant Design Vue、Node Test Runner、Vite

---

### Task 1: 锁定工作流页面的前端表面

**Files:**
- Create: `frontend/test/aidd-workflow-surface.test.ts`
- Test: `frontend/test/aidd-workflow-surface.test.ts`

**Step 1: Write the failing test**

编写静态表面测试，断言以下能力将要出现：

- 路由中存在 `/workflow`
- 首页或工具列表页存在流程工作台入口
- 存在 `frontend/src/stores/workflow.ts`
- 存在 `frontend/src/workflow/aidd-catalog.ts`
- 存在 `frontend/src/views/workflow/index.vue`

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/aidd-workflow-surface.test.ts"`
Expected: FAIL，因为当前还不存在流程工作台页面和相关模块。

### Task 2: 建立工作流配置与类型骨架

**Files:**
- Create: `frontend/src/workflow/aidd-catalog.ts`
- Create: `frontend/src/workflow/artifact-types.ts`
- Create: `frontend/src/workflow/tool-bindings.ts`
- Modify: `frontend/src/types/models.d.ts`
- Test: `frontend/test/aidd-workflow-surface.test.ts`

**Step 1: Write minimal implementation**

- 在 `artifact-types.ts` 中定义：
  - 五个步骤 key
  - 步骤状态类型
  - 产物语义类型
  - 工作流会话与步骤数据结构
- 在 `aidd-catalog.ts` 中定义固定五步顺序与步骤下工具 slug 列表
- 在 `tool-bindings.ts` 中建立首批工具绑定配置骨架
- 只在 `models.d.ts` 中补最小公共类型，避免污染现有工具模型

**Step 2: Run test to verify partial pass**

Run: `node --test "frontend/test/aidd-workflow-surface.test.ts"`
Expected: 配置文件存在相关断言转绿，路由与页面断言仍失败。

### Task 3: 为工作流逻辑建立纯函数测试基线

**Files:**
- Create: `frontend/test/aidd-workflow-logic.test.ts`
- Test: `frontend/test/aidd-workflow-logic.test.ts`

**Step 1: Write the failing test**

编写纯逻辑测试，覆盖：

- 从多个候选产物中选择最新有效结果
- 上一步成功后下一步变为 `ready`
- 上游重跑后下游步骤变为 `invalidated`
- 恢复时原工具不存在会进入 `needs_tool_selection`

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/aidd-workflow-logic.test.ts"`
Expected: FAIL，因为解析器和状态规则尚未实现。

### Task 4: 实现产物解析与步骤状态规则

**Files:**
- Create: `frontend/src/workflow/artifact-resolver.ts`
- Create: `frontend/src/workflow/workflow-state.ts`
- Test: `frontend/test/aidd-workflow-logic.test.ts`

**Step 1: Write minimal implementation**

- 在 `artifact-resolver.ts` 中实现：
  - 按语义类型筛选候选产物
  - 优先选择最新有效产物
  - 处理多候选的默认选择规则
- 在 `workflow-state.ts` 中实现：
  - 根据产物与工具选择计算步骤状态
  - 标记下游失效
  - 恢复失配工具时进入 `needs_tool_selection`

**Step 2: Run test to verify it passes**

Run: `node --test "frontend/test/aidd-workflow-logic.test.ts"`
Expected: PASS

### Task 5: 新增持久化的工作流 Store

**Files:**
- Create: `frontend/src/stores/workflow.ts`
- Modify: `frontend/src/stores/index.ts`
- Test: `frontend/test/aidd-workflow-surface.test.ts`

**Step 1: Write the failing test**

在 `frontend/test/aidd-workflow-surface.test.ts` 中补充断言：

- `stores/index.ts` 导出 `useWorkflowStore`
- `workflow.ts` 启用了持久化配置
- `workflow.ts` 中存在 `sessionId`、`activeStepKey`、`artifacts`、`taskByStep`

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/aidd-workflow-surface.test.ts"`
Expected: FAIL，因为 store 尚未实现。

**Step 3: Write minimal implementation**

- 新增 `useWorkflowStore`
- 保存工作流会话、步骤草稿、步骤任务、产物池
- 使用 `persist` 做本地持久化
- 提供 `resetSession()`、`selectTool()`、`recordTask()`、`registerArtifacts()` 等最小动作

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/aidd-workflow-surface.test.ts"`
Expected: store 相关断言 PASS。

### Task 6: 新增工作流页面路由与入口

**Files:**
- Create: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/views/home/index.vue`
- Modify: `frontend/src/views/tools/List.vue`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Test: `frontend/test/aidd-workflow-surface.test.ts`

**Step 1: Write the failing test**

补充表面测试，断言：

- 路由包含 `/workflow`
- 首页包含“进入流程工作台”入口
- 工具列表页包含“按流程使用工具”入口
- locale 中新增工作流标题、入口文案和步骤文案

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/aidd-workflow-surface.test.ts"`
Expected: FAIL，因为路由与入口尚未添加。

**Step 3: Write minimal implementation**

- 新增 `/workflow` 路由
- 首页 AIDD 区新增工作流 CTA
- 工具列表页头新增次级入口按钮
- 补齐中英文文案键
- 页面先提供静态三栏骨架和占位内容

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/aidd-workflow-surface.test.ts"`
Expected: PASS

### Task 7: 拆出工作流页面子组件骨架

**Files:**
- Create: `frontend/src/components/workflow/WorkflowStepSidebar.vue`
- Create: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Create: `frontend/src/components/workflow/WorkflowArtifactPanel.vue`
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/test/aidd-workflow-surface.test.ts`

**Step 1: Write the failing test**

补充静态测试，断言工作流页已拆为：

- 步骤侧栏组件
- 运行面板组件
- 产物面板组件

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/aidd-workflow-surface.test.ts"`
Expected: FAIL，因为当前只有页面骨架。

**Step 3: Write minimal implementation**

- 新建三个组件文件
- 在 `index.vue` 中串联三栏布局
- 先把步骤、工具、空态和占位信息打通

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/aidd-workflow-surface.test.ts"`
Expected: PASS

### Task 8: 在工作流页接入工具查询与步骤工具映射

**Files:**
- Modify: `frontend/src/api/tools.ts`
- Modify: `frontend/src/stores/tools.ts`
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/components/workflow/WorkflowStepSidebar.vue`
- Modify: `frontend/src/workflow/aidd-catalog.ts`
- Modify: `frontend/src/workflow/tool-bindings.ts`
- Test: `frontend/test/aidd-workflow-logic.test.ts`

**Step 1: Write the failing test**

补充逻辑或表面测试，断言：

- 工作流步骤只展示配置命中的工具 slug
- 缺失工具会显示“暂未上线”
- 当前步骤存在推荐工具默认选中策略

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/aidd-workflow-logic.test.ts"`
Expected: FAIL，因为步骤工具解析规则尚未落地。

**Step 3: Write minimal implementation**

- 复用现有 `getToolList` / `getToolDetail`
- 在工作流页对公开工具列表做 slug 映射
- 为步骤构造“可用工具 + 缺失工具”视图模型
- 首批只对工作流配置中显式列出的工具进行承接支持

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/aidd-workflow-logic.test.ts"`
Expected: PASS

### Task 9: 在工作流页复用现有 schema 表单渲染能力

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Modify: `frontend/src/views/tools/detail-schema.ts`
- Modify: `frontend/src/types/models.d.ts`
- Test: `frontend/test/aidd-workflow-surface.test.ts`

**Step 1: Write the failing test**

补充表面测试，断言：

- 工作流运行面板复用了 `flattenToolInputSchema`
- 工作流运行面板存在文件上传、参数提交、重置表单入口
- 页面支持显示当前自动绑定来源

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/aidd-workflow-surface.test.ts"`
Expected: FAIL，因为运行面板仍是静态占位。

**Step 3: Write minimal implementation**

- 在工作流运行面板中接入真实工具 schema
- 复用 `flattenToolInputSchema` 与 `buildTaskSubmissionPayload`
- 支持表单草稿按步骤保存
- 支持文件上传与工具参数填写

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/aidd-workflow-surface.test.ts"`
Expected: PASS

### Task 10: 接入任务创建与轮询状态更新

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Modify: `frontend/src/stores/workflow.ts`
- Modify: `frontend/src/api/tasks.ts`
- Test: `frontend/test/aidd-workflow-logic.test.ts`

**Step 1: Write the failing test**

补充逻辑测试，断言：

- 提交任务后当前步骤变为 `running`
- 任务成功后当前步骤变为 `completed`
- 任务失败后当前步骤变为 `failed`

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/aidd-workflow-logic.test.ts"`
Expected: FAIL，因为任务状态流转尚未实现。

**Step 3: Write minimal implementation**

- 调用现有 `createTask`
- 以轮询方式调用 `getTaskDetail`
- 同步当前步骤的任务状态、进度和结果摘要
- 保留失败后的草稿和输入来源

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/aidd-workflow-logic.test.ts"`
Expected: PASS

### Task 11: 产出标准化产物并实现自动带入

**Files:**
- Modify: `frontend/src/workflow/tool-bindings.ts`
- Modify: `frontend/src/workflow/artifact-resolver.ts`
- Modify: `frontend/src/stores/workflow.ts`
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowArtifactPanel.vue`
- Test: `frontend/test/aidd-workflow-logic.test.ts`

**Step 1: Write the failing test**

补充逻辑测试，覆盖：

- 口袋预测成功后登记 `pocket_structure`
- 下一步工具进入时自动绑定最新 `pocket_structure`
- 当同一语义存在多个候选时，默认选择最新结果但允许切换

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/aidd-workflow-logic.test.ts"`
Expected: FAIL，因为标准化产物与自动带入尚未实现。

**Step 3: Write minimal implementation**

- 为已接入工作流的工具实现显式输出提取规则
- 将任务结果转换为标准化产物
- 进入下一步时按语义类型做自动绑定
- 右侧面板展示产物来源与默认绑定状态

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/aidd-workflow-logic.test.ts"`
Expected: PASS

### Task 12: 实现失效传播、恢复与重置流程

**Files:**
- Modify: `frontend/src/stores/workflow.ts`
- Modify: `frontend/src/workflow/workflow-state.ts`
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Test: `frontend/test/aidd-workflow-logic.test.ts`

**Step 1: Write the failing test**

补充逻辑测试，覆盖：

- 上游步骤重跑后，下游已完成步骤变为 `invalidated`
- 恢复流程时原工具不存在会进入 `needs_tool_selection`
- 用户可执行“新建流程”重置本地状态

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/aidd-workflow-logic.test.ts"`
Expected: FAIL，因为失效传播和恢复逻辑尚未实现。

**Step 3: Write minimal implementation**

- 在 store 中实现下游失效传播
- 页面顶部新增“新建流程”与“恢复当前流程”动作
- 恢复时校验 `ownerUserId`、工具可用性和产物完整性

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/aidd-workflow-logic.test.ts"`
Expected: PASS

### Task 13: 完成文案、空态与异常提示

**Files:**
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Modify: `frontend/src/components/workflow/WorkflowStepSidebar.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowArtifactPanel.vue`
- Test: `frontend/test/aidd-workflow-surface.test.ts`

**Step 1: Write the failing test**

补充静态测试，断言页面包含以下文案或状态：

- 进入流程工作台
- 新建流程
- 恢复当前流程
- 暂未上线
- 缺少上游产物
- 结果已失效

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/aidd-workflow-surface.test.ts"`
Expected: FAIL，因为异常提示与空态尚未补齐。

**Step 3: Write minimal implementation**

- 补齐工作流专用文案
- 为缺失工具、缺失输入、结果失效、恢复异常提供明确提示
- 保持桌面端与移动端都能读清当前状态

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/aidd-workflow-surface.test.ts"`
Expected: PASS

### Task 14: 回归验证与构建验证

**Files:**
- No code changes

**Step 1: Run workflow tests**

Run:
- `node --test "frontend/test/aidd-workflow-surface.test.ts"`
- `node --test "frontend/test/aidd-workflow-logic.test.ts"`

Expected: PASS

**Step 2: Run existing related tests**

Run:
- `node --test "frontend/test/home-cpupdb-aidd.test.ts"`
- `node --test "frontend/test/task-result-visualization.test.ts"`
- `node --test "frontend/test/product-surface-pruning.test.ts"`

Expected: PASS，确认没有破坏首页流程区、任务可视化和已裁剪的主流程表面。

**Step 3: Run frontend build**

Run: `npm run build`
Workdir: `frontend`
Expected: exit 0

## 备注

- 按仓库当前协作约束，本计划不包含自动 `git commit` 步骤。
- 若后续升级为后端持久化工作流，优先复用本次的 `session`、`artifact`、`step state` 结构，不要推翻前端语义模型。
