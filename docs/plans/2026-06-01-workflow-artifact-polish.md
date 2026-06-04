# Workflow Artifact Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把工作台产物复用与浏览改造成更顺手的路径式交互，在保留四级层级规则的前提下，实现左侧 `路径条 + 单层选择` 和右侧分组展开式浏览，并支持从面板反向定位选择器。

**Architecture:** 继续复用现有共享四级树派生器，不改后端和层级归属规则。左侧选择器新增步骤态与路径条，右侧面板新增本地展开状态和路径回传事件，工作台页负责最小化协调左右联动。

**Tech Stack:** Vue 3、TypeScript、Pinia、Ant Design Vue、Node Test Runner、Vite

---

### Task 1: 为交互打磨补失败测试

**Files:**
- Modify: `frontend/test/workflow-artifact-hierarchy.test.ts`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`

**Step 1: Write the failing test**

扩展现有表面断言，覆盖：

- `ArtifactFilePicker.vue` 出现路径条类名与步骤态状态
- `WorkflowArtifactPanel.vue` 出现分组/工具/任务折叠结构与路径选择事件
- 选择器与面板都继续消费共享层级派生器

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`

Expected: FAIL，因为当前组件还没有路径条、步骤态和面板联动入口

### Task 2: 实现左侧路径条与单层选择

**Files:**
- Modify: `frontend/src/components/tools/ArtifactFilePicker.vue`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`

**Step 1: Add step state**

在选择器中新增：

- `activeStep`
- 路径条回退处理函数
- 候选项列表派生逻辑

**Step 2: Replace four-parallel-select UI**

把并列四个下拉改成：

- `artifact-path`
- `artifact-step-panel`
- `artifact-selection-summary`

保留现有数据状态字段，避免无谓重写。

**Step 3: Keep selection backfill**

确保已有产物仍可反查并回填完整路径。

**Step 4: Run test**

Run: `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`

Expected: PASS

### Task 3: 实现右侧分组展开与路径回传

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowArtifactPanel.vue`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`

**Step 1: Add local expand state**

为分组、工具、任务增加本地展开状态，并按当前上下文初始化默认展开。

**Step 2: Add path emit**

为任务或产物点击增加路径事件，携带：

- `groupId`
- `toolSlug`
- `taskId`
- `artifactId?`

**Step 3: Compact artifact rendering**

把任务卡改成“摘要先行，产物后展开”的节奏，避免面板继续无边界增长。

**Step 4: Run test**

Run: `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`

Expected: PASS

### Task 4: 在工作台内接入左右联动

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`

**Step 1: Add local sync state**

在最小范围内保存最近一次从右侧点击得到的路径。

**Step 2: Wire picker inputs**

把路径同步给左侧选择器，使其自动定位到对应的：

- 分组
- 工具
- 任务
- 产物

**Step 3: Keep current defaults**

保留现有“当前分组 + 当前工具”的默认定位优先级；若有显式路径，则显式路径优先。

**Step 4: Run test**

Run: `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`

Expected: PASS

### Task 5: 回归验证与构建检查

**Files:**
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`
- Test: `frontend/test/task-name-surface.test.ts`

**Step 1: Run targeted tests**

Run:

- `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`
- `node --test "frontend/test/task-name-surface.test.ts"`

Expected:

- PASS

**Step 2: Run build**

Run: `npm run build`

Workdir: `frontend/`

Expected:

- Build succeeds
- 允许保留既有非阻塞 Vite 警告，但不能新增错误
