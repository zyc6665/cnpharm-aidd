# Workflow Workbench Visual Refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> **Session note:** 按当前仓库协作约束执行，本计划不包含 `git commit`、分支或 worktree 步骤。

**Goal:** 修复工具工作台“我的产物”中任务 ID 竖排拉长卡片的问题，并将 `/workflow` 三栏统一成更完整、更美观的浅色实验工作台。

**Architecture:** 后端仅为产物接口增加 `task_name` 最小字段，前端继续复用现有四级层级派生器，把任务节点改成“任务名主标题，短 ID 次信息”，并在页面壳层、左栏分组、中栏运行面板、右栏产物面板上统一视觉语义。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic、Vue 3、TypeScript、Pinia、Ant Design Vue、Pytest、Node Test Runner、Vite

---

### Task 1: 为产物接口的任务名能力建立失败测试

**Files:**
- Modify: `test/test_file_artifacts_api.py`
- Test: `test/test_file_artifacts_api.py`

**Step 1: Write the failing test**

扩展现有 `/api/v1/files/artifacts` 接口测试，覆盖：

- 返回项包含 `task_name`
- 有任务名时返回真实名称
- 无任务名时返回 `null` 或兼容回退值，但接口不报错

**Step 2: Run test to verify it fails**

Run: `pytest test/test_file_artifacts_api.py -q`

Expected: FAIL，因为当前 schema 和响应体里还没有 `task_name`

### Task 2: 实现后端产物接口补 `task_name`

**Files:**
- Modify: `backend/app/schemas/files.py`
- Modify: `backend/app/api/v1/files.py`
- Test: `test/test_file_artifacts_api.py`

**Step 1: Add schema field**

在 `ArtifactFileResponse` 中新增：

```python
task_name: Optional[str] = Field(None, description="任务名称")
```

**Step 2: Fill response data**

在 `/files/artifacts` 的返回构造逻辑中，将关联任务的 `task.name` 写入响应；若缺失则保持 `None`，不要在这里重新引入复杂命名逻辑。

**Step 3: Run test**

Run: `pytest test/test_file_artifacts_api.py -q`

Expected: PASS

### Task 3: 为工作台任务卡语义与层级展示建立失败测试

**Files:**
- Modify: `frontend/test/workflow-artifact-hierarchy.test.ts`
- Modify: `frontend/test/tool-workbench-surface.test.ts`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`
- Test: `frontend/test/tool-workbench-surface.test.ts`

**Step 1: Write the failing test**

补充前端表面断言，覆盖：

- `ArtifactFile` 类型包含 `task_name`
- `artifact-hierarchy.ts` 会把 `task_name` 写入任务节点
- `WorkflowArtifactPanel.vue` 的任务卡优先展示任务名，而不是长 `task_id`
- 任务次信息区包含短 ID 语义
- 工作台页存在统一舱体/甲板类名，而不是零散默认块

**Step 2: Run tests to verify they fail**

Run:

- `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`
- `node --test "frontend/test/tool-workbench-surface.test.ts"`

Expected: FAIL，因为当前实现还没有这些语义和样式壳层

### Task 4: 实现任务名优先与短 ID 次信息

**Files:**
- Modify: `frontend/src/types/models.d.ts`
- Modify: `frontend/src/workflow/artifact-hierarchy.ts`
- Modify: `frontend/src/components/workflow/WorkflowArtifactPanel.vue`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`

**Step 1: Extend types**

在 `ArtifactFile` 中增加：

```ts
task_name?: string
```

并在层级节点中保留 `taskName` 字段。

**Step 2: Populate hierarchy task metadata**

在构树逻辑里优先写入：

- `taskName`
- `taskShortId`
- `latestArtifactAt`

保证任务节点可以脱离长 UUID 直接渲染。

**Step 3: Refactor task card rendering**

将右侧任务节点改成：

- 主标题：任务名
- 次信息：`#短ID · 时间 · 产物数`
- 展开区：产物列表

删除或避开 `artifact-task-id` 上的 `overflow-wrap: anywhere`，避免 UUID 逐字符断裂。

**Step 4: Run test**

Run: `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`

Expected: PASS

### Task 5: 统一工作台三栏视觉壳层

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/components/workflow/WorkflowStepSidebar.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowArtifactPanel.vue`
- Test: `frontend/test/tool-workbench-surface.test.ts`

**Step 1: Add shared page shell**

为 `/workflow` 页面增加统一的实验工作台背景、容器宽度、三栏间距和列级舱体类名。

**Step 2: Polish sidebar**

左栏分组卡统一成研究主题卡：

- 更清晰的激活态
- 一致的标签胶囊
- 更稳的 sticky 和滚动边界

**Step 3: Polish run panel**

中栏整理为连续的参数台结构：

- 分组横幅
- 工具选择
- 工具摘要
- 参数表单
- 提交底栏

**Step 4: Polish artifact panel**

右栏分组、工具、任务、产物层级统一成同系卡片语言，压缩垂直噪音并增强信息层级。

**Step 5: Run test**

Run: `node --test "frontend/test/tool-workbench-surface.test.ts"`

Expected: PASS

### Task 6: 回归验证与构建检查

**Files:**
- Test: `test/test_file_artifacts_api.py`
- Test: `frontend/test/workflow-artifact-hierarchy.test.ts`
- Test: `frontend/test/tool-workbench-surface.test.ts`

**Step 1: Run targeted tests**

Run:

- `pytest test/test_file_artifacts_api.py -q`
- `node --test "frontend/test/workflow-artifact-hierarchy.test.ts"`
- `node --test "frontend/test/tool-workbench-surface.test.ts"`

Expected:

- PASS

**Step 2: Run build**

Run: `npm run build`

Workdir: `frontend/`

Expected:

- Build succeeds
- 允许保留既有非阻塞 Vite 警告，但不能新增错误
