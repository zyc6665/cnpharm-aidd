# Workflow Artifact Hierarchy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让工作台中的参数产物复用选择器和右侧产物面板统一展示 `工具分组 -> 工具 -> 任务 -> 任务产物` 四级层级，并按工作台分组顺序为多分组工具确定唯一主分组。

**Architecture:** 在前端新增一个共享的产物层级派生器，统一消费 `WorkbenchGroup[]` 与 `ArtifactFile[]`，产出稳定的四级树。参数选择器改为四级级联选择，右侧产物面板改为按同一棵树渲染当前分组视角和全局最近视角，避免两套分组逻辑并行。

**Tech Stack:** Vue 3、TypeScript、Pinia、Ant Design Vue、Node Test Runner、Vite

---

### Task 1: 为共享四级树派生器建立失败测试

**Files:**
- Create: `frontend/test/workflow-artifact-hierarchy.test.ts`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`

**Step 1: Write the failing test**

在 `frontend/test/workflow-artifact-hierarchy.test.ts` 中准备最小样例数据：

- 两个工作台分组
- 三个工具，其中一个工具同时存在于两个分组
- 若干任务产物，覆盖多个工具、多个任务

至少覆盖以下断言：

- 同一个 `toolSlug` 命中多个分组时，只归到首个匹配分组
- 返回结果包含 `group -> tool -> task -> artifact` 四级结构
- 任务按最新产物时间倒序
- 产物按创建时间倒序
- `accept` 过滤后空任务、空工具、空分组会被裁掉
- 不属于任何工作台分组的工具在“全局视角”下进入 `ungrouped` 节点

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`

Expected:

- FAIL，因为共享四级树派生器还不存在

**Step 3: 记录失败原因**

确认失败来自：

- 缺少模块
- 缺少导出函数

不要在这一步顺手修改业务组件。

### Task 2: 实现共享四级树派生器

**Files:**
- Create: `frontend/src/workflow/artifact-hierarchy.ts`
- Modify: `frontend/src/components/tools/artifact-selection.ts`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`

**Step 1: 写最小实现**

在 `frontend/src/workflow/artifact-hierarchy.ts` 中定义共享类型：

- `WorkflowArtifactGroupNode`
- `WorkflowArtifactToolNode`
- `WorkflowArtifactTaskNode`
- `WorkflowArtifactHierarchyScope`

实现函数：

- `buildWorkflowArtifactHierarchy(...)`
- `buildPrimaryGroupMap(...)`
- `groupArtifactsIntoHierarchy(...)`

最小输入建议：

```ts
buildWorkflowArtifactHierarchy({
  groups,
  artifacts,
  accept,
  scope
})
```

实现规则：

- 先复用 `filterCompatibleArtifacts(...)`
- 按工作台分组顺序建立 `toolSlug -> primaryGroup`
- 根据 `artifact.tool_slug` 把任务归入主分组
- `scope: 'current-group'` 时只保留当前分组
- `scope: 'global'` 时保留全部分组，并为未归属工具建立虚拟分组

同时把 `artifact-selection.ts` 里当前面向任务的逻辑收敛为可复用工具函数，不要复制噪音过滤和 `accept` 过滤实现。

**Step 2: Run test to verify it passes**

Run: `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`

Expected:

- PASS，四级树派生逻辑通过

**Step 3: 做一次最小回归检查**

Run: `node --test "frontend/test/task-name-surface.test.ts"`

Expected:

- PASS，说明现有任务命名表面能力未被影响

### Task 3: 为参数选择器四级级联建立失败测试

**Files:**
- Modify: `frontend/test/workflow-artifact-hierarchy.test.ts`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`

**Step 1: 扩展表面断言**

增加针对 [ArtifactFilePicker.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/components/tools/ArtifactFilePicker.vue) 的源码表面断言，至少覆盖：

- 存在 `selectedGroupId`
- 存在 `selectedToolSlug`
- 保留 `selectedTaskId`
- 模板中出现四个选择层级
- 已选产物回填逻辑会同时同步分组、工具、任务

如果当前项目更适合源码字符串断言，就保持一致，不强行上渲染测试框架。

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`

Expected:

- FAIL，因为参数选择器仍然只有 `任务 -> 产物`

### Task 4: 实现参数选择器四级级联

**Files:**
- Modify: `frontend/src/components/tools/ArtifactFilePicker.vue`
- Modify: `frontend/src/views/tools/Detail.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`

**Step 1: 重构选择器状态**

在 `ArtifactFilePicker.vue` 中新增：

- `selectedGroupId`
- `selectedToolSlug`
- 保留 `selectedTaskId`

并把现有按任务分组的 `artifactTaskGroups` 替换为基于共享四级树的：

- `groupNodes`
- `selectedGroupNode`
- `selectedToolNode`
- `selectedTaskNode`
- `selectedTaskArtifacts`

**Step 2: 修改模板为四级级联**

模板增加：

- 分组选择 `a-select`
- 工具选择 `a-select`
- 任务选择 `a-select`
- 产物选择 `a-select`

层级联动规则：

- 上层变化时清空所有下层
- 当前下层若仍然有效则保留，否则清空

**Step 3: 实现已选产物回填**

基于共享四级树反查当前 `selectedArtifact`：

- 定位其 `groupId`
- 定位其 `toolSlug`
- 定位其 `taskId`
- 最终定位产物本身

同步更新本地选择状态。

**Step 4: 为工作台默认定位补输入**

如果需要最小化额外耦合，给 `ArtifactFilePicker.vue` 增加可选 props：

- `preferredGroupId?: string | null`
- `preferredToolSlug?: string | null`

让工作台运行面板传入当前激活分组和当前工具，用于默认定位；普通工具详情页不传。

**Step 5: Run tests**

Run:

- `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`
- `node --test "frontend/test/task-name-surface.test.ts"`

Expected:

- PASS

### Task 5: 为产物面板统一四级层级建立失败测试

**Files:**
- Modify: `frontend/test/workflow-artifact-hierarchy.test.ts`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`

**Step 1: 增加产物面板表面断言**

覆盖 [WorkflowArtifactPanel.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/components/workflow/WorkflowArtifactPanel.vue)：

- 不再只按任务卡片分组
- 组件消费共享四级树派生器
- 模板存在 `group -> tool -> task -> artifact` 渲染结构
- 当前分组视角与全局最近视角都从共享树派生

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`

Expected:

- FAIL，因为右侧面板仍然是内部 `groupArtifactsByTask(...)` 逻辑

### Task 6: 实现产物面板统一四级层级

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowArtifactPanel.vue`
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`

**Step 1: 替换内部任务分组逻辑**

删除或停止使用组件内部的 `groupArtifactsByTask(...)`，改为：

- 基于共享四级树派生当前分组视角
- 基于共享四级树派生全局视角

**Step 2: 重构模板层级**

展示结构改成：

- 分组区块
- 工具 section
- 任务卡片
- 任务卡片内的产物列表

保留已有能力：

- `查看任务`
- 最新任务摘要
- `刷新`

但不要再让“当前分组”和“最近产物”各自维护不同的任务分组逻辑。

**Step 3: 处理未分组工具**

在全局视角中：

- 如果共享树返回了 `ungrouped` 分组，则渲染为单独区块

在当前分组视角中：

- 不展示未分组工具

**Step 4: Run tests**

Run:

- `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`
- `node --test "frontend/test/task-name-surface.test.ts"`

Expected:

- PASS

### Task 7: 统一文案与类型边界

**Files:**
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Modify: `frontend/src/types/models.d.ts`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`

**Step 1: 补充分组/工具/任务/产物层级文案**

如果当前 locale 中缺少以下文案，则补齐：

- 选择分组
- 选择工具
- 选择任务
- 未分组工具
- 无兼容产物

**Step 2: 检查类型是否需要补充**

如果参数选择器或面板需要显式的前端层级类型导出，则只在最小范围内补齐，不要把工作台派生结构塞回后端模型类型。

**Step 3: Run tests**

Run: `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`

Expected:

- PASS

### Task 8: 做完整验证

**Files:**
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`
- Test: `frontend/test/task-name-surface.test.ts`

**Step 1: 运行目标测试**

Run:

- `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`
- `node --test "frontend/test/task-name-surface.test.ts"`

Expected:

- 全部 PASS

**Step 2: 运行前端构建**

Run: `npm run build`

Workdir:

- `frontend/`

Expected:

- 构建成功
- 若仍有既有 Vite warning，可以记录，但不能有新增错误

**Step 3: 人工验收清单**

手动确认：

- 工作台参数复用选择器是 `分组 -> 工具 -> 任务 -> 产物`
- 当前工作台分组默认定位正确
- 同一个工具命中多个分组时只出现一次
- 右侧产物面板也按四级结构展示
- 点击“查看任务”仍能正常跳转

---

Plan complete and saved to `docs/plans/2026-05-31-workflow-artifact-hierarchy.md`.

两种执行方式：

1. `推荐` 当前会话直接执行  
浮浮酱按这份计划逐步实现，边改边测，保留每一步的验证结果。

2. 单独会话执行  
在新会话里按计划独立落地，适合把实现过程和当前讨论拆开。
