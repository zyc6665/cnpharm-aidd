# Workflow Inline Results Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> **Session note:** 按当前仓库协作约束执行，本计划不包含 `git commit`、分支或 worktree 步骤。

**Goal:** 在工具工作台中栏表单下方增加轻量结果面板，让任务运行完成后即可在 `/workflow` 内查看结果可视化、输出数据、输出文件和关键日志，而不必先跳转任务详情页。

**Architecture:** 复用现有任务详情页中的成熟结果能力，不复制整页详情。新增工作台专用 `WorkflowTaskResultPanel` 作为轻量容器，抽取共享的输出摘要与日志预览块，由工作台页协调当前结果任务上下文，并与右侧“我的产物”联动切换。

**Tech Stack:** Vue 3、TypeScript、Pinia、Vue Router、Ant Design Vue、Node Test Runner、Vite

---

### Task 1: 为工作台内联结果区补失败测试

**Files:**
- Modify: `frontend/test/tool-workbench-surface.test.ts`
- Create or Modify: `frontend/test/workflow-inline-results.test.ts`
- Test: `frontend/test/workflow-inline-results.test.ts`

**Step 1: Write the failing test**

覆盖以下断言：

- `WorkflowRunPanel.vue` 挂载工作台结果面板
- 结果面板保留“查看完整任务详情”入口
- 结果面板继续引用 `ResultVisualizationPanel`
- 工作台页存在当前结果任务上下文与右侧联动入口

**Step 2: Run test to verify it fails**

Run:

- `node --test "frontend/test/workflow-inline-results.test.ts"`

Expected:

- FAIL，因为工作台当前还没有内联结果面板

### Task 2: 抽取共享输出摘要与日志预览组件

**Files:**
- Create: `frontend/src/components/tasks/TaskOutputSummary.vue`
- Create: `frontend/src/components/tasks/TaskLogPreview.vue`
- Modify: `frontend/src/views/tasks/Detail.vue`
- Test: `frontend/test/workflow-inline-results.test.ts`

**Step 1: Write minimal shared components**

抽离任务详情页中稳定的两块：

- 输出数据 + 输出文件
- 日志预览

避免在工作台和任务详情页维护两套模板。

**Step 2: Reuse in task detail page**

先让任务详情页改为消费新组件，保证抽离后的组件边界正确。

**Step 3: Run test**

Run:

- `node --test "frontend/test/workflow-inline-results.test.ts"`

Expected:

- 仍可能 FAIL，因为工作台尚未接入这些组件

### Task 3: 新增工作台轻量结果面板组件

**Files:**
- Create: `frontend/src/components/workflow/WorkflowTaskResultPanel.vue`
- Modify: `frontend/src/api/tasks.ts`
- Modify: `frontend/src/stores/tasks.ts`
- Test: `frontend/test/workflow-inline-results.test.ts`

**Step 1: Add lightweight result panel**

实现 `WorkflowTaskResultPanel.vue`，负责：

- 根据 `taskId` 加载完整任务详情
- 渲染 `pending/running/success/failure` 四种结果态
- 组合：
  - `ResultVisualizationPanel`
  - `TaskOutputSummary`
  - `TaskLogPreview`

**Step 2: Keep minimal data fetching**

优先读取已有任务状态；若结果不完整，再调用 `getTaskDetail(taskId)` 补全详情。不要把整套详情页逻辑直接复制进来。

**Step 3: Add detail entry**

保留 `查看完整任务详情` 按钮，跳转 `/tasks/:id`。

**Step 4: Run test**

Run:

- `node --test "frontend/test/workflow-inline-results.test.ts"`

Expected:

- 结果面板语义测试通过

### Task 4: 在工作台页接入结果上下文与右侧联动

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowArtifactPanel.vue`
- Test: `frontend/test/workflow-inline-results.test.ts`

**Step 1: Add active result task context**

在工作台页新增轻量状态：

- `activeResultTaskId`

默认指向当前工具最近任务。

**Step 2: Wire run panel result zone**

把结果面板挂载到 `WorkflowRunPanel.vue` 的提交区下方，让运行、状态、结果在同一列闭环。

**Step 3: Keep right-panel switching**

当右侧“我的产物”点击任务或产物时：

- 若属于当前工具，直接切换 `activeResultTaskId`
- 若属于其他工具，先切分组和工具，再同步结果任务

**Step 4: Run test**

Run:

- `node --test "frontend/test/workflow-inline-results.test.ts"`

Expected:

- PASS

### Task 5: 工作台结果区样式打磨

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowTaskResultPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Modify: `frontend/src/components/tasks/TaskOutputSummary.vue`
- Modify: `frontend/src/components/tasks/TaskLogPreview.vue`
- Test: `frontend/test/tool-workbench-surface.test.ts`

**Step 1: Match workbench visual language**

结果区样式统一到当前工作台浅色实验甲板风格：

- 与中栏表单壳层一致
- 与右栏产物卡一致
- 状态、输出、日志保持清晰分段

**Step 2: Prevent visual overload**

日志默认只显示关键预览，不把完整详情页的信息密度直接搬进工作台。

**Step 3: Run test**

Run:

- `node --test "frontend/test/tool-workbench-surface.test.ts"`

Expected:

- PASS

### Task 6: 回归验证与构建检查

**Files:**
- Test: `frontend/test/workflow-inline-results.test.ts`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`
- Test: `frontend/test/tool-workbench-surface.test.ts`
- Test: `frontend/test/task-name-surface.test.ts`

**Step 1: Run targeted tests**

Run:

- `node --test "frontend/test/workflow-inline-results.test.ts"`
- `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`
- `node --test "frontend/test/tool-workbench-surface.test.ts"`
- `node --test "frontend/test/task-name-surface.test.ts"`

Expected:

- PASS

**Step 2: Run build**

Run: `npm run build`

Workdir: `frontend/`

Expected:

- Build succeeds
- 允许保留既有非阻塞 Vite 警告，但不能新增错误
