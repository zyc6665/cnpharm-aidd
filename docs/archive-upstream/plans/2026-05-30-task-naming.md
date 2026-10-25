# Task Naming Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为任务系统增加可选任务名、默认任务名生成、任务名展示与按任务名搜索能力，并让单工具页和工作台两个任务创建入口保持一致。

**Architecture:** 后端为 `Task` 增加持久化 `name` 字段，并在创建与响应层统一处理默认命名和旧任务回退展示。前端在所有任务创建入口新增可选输入框，列表和详情优先展示 `task.name`，同时扩展类型和工作台任务引用结构。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic、Vue 3、TypeScript、Pinia、Ant Design Vue、Pytest、Node Test Runner、Vite

---

### Task 1: 为后端任务命名行为建立失败测试

**Files:**
- Create: `test/test_task_naming.py`
- Test: `test/test_task_naming.py`

**Step 1: Write the failing test**

在 `test/test_task_naming.py` 中创建隔离数据库和 API 客户端，覆盖以下场景：

- `POST /api/v1/tasks` 传入 `name` 时，响应 `data.name` 为该值
- `POST /api/v1/tasks` 不传 `name` 时，响应 `data.name` 不是空，且包含工具名
- `GET /api/v1/tasks` 返回条目包含 `name`
- `GET /api/v1/tasks?keyword=<任务名>` 能命中对应任务
- 直接插入 `name is NULL` 的旧任务后，`GET /api/v1/tasks/{id}` 仍返回非空 `name`

**Step 2: Run test to verify it fails**

Run: `pytest test/test_task_naming.py -v`
Expected: FAIL，因为 `Task`、schema 和 API 还没有任务名能力。

**Step 3: Commit**

```bash
git add test/test_task_naming.py
git commit -m "test: add task naming api coverage"
```

### Task 2: 实现后端任务命名模型、schema 与 API

**Files:**
- Modify: `backend/app/models/tasks.py`
- Modify: `backend/app/schemas/tasks.py`
- Modify: `backend/app/api/v1/tasks.py`
- Test: `test/test_task_naming.py`

**Step 1: Write minimal implementation**

在 `backend/app/models/tasks.py` 的 `Task` 中增加：

```python
name = Column(String(120), nullable=True, index=True)
```

在 `backend/app/schemas/tasks.py` 中增加：

```python
class TaskCreate(BaseModel):
    name: Optional[str] = Field(None, description="任务名称")
```

并在 `TaskResponse`、`TaskListResponse` 中加入 `name: Optional[str]`。

在 `backend/app/api/v1/tasks.py` 中新增最小 helper：

```python
def _sanitize_task_name(name: Optional[str]) -> Optional[str]:
    if name is None:
        return None
    normalized = name.strip()
    return normalized or None
```

```python
def _build_default_task_name(tool_name: Optional[str], created_at: datetime, task_id: str) -> str:
    if tool_name:
        return f"{tool_name} {created_at.strftime('%Y-%m-%d %H:%M')}"
    return f"任务 {task_id[:8]}"
```

```python
def _resolve_task_display_name(task: Task, tool_name: Optional[str]) -> str:
    if task.name:
        return task.name
    return _build_default_task_name(tool_name, task.created_at, task.id)
```

创建任务时：

- 先保存清洗后的 `task_data.name`
- `flush()` 后若为空则用 helper 生成默认名称并写回 `task.name`

列表与详情返回时：

- 始终回填 `name = _resolve_task_display_name(...)`

列表搜索时扩展：

```python
Task.name.ilike(search_pattern)
```

**Step 2: Run test to verify it passes**

Run: `pytest test/test_task_naming.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/app/models/tasks.py backend/app/schemas/tasks.py backend/app/api/v1/tasks.py test/test_task_naming.py
git commit -m "feat: add task naming support to tasks api"
```

### Task 3: 为已有数据库补字段脚本并建立失败测试

**Files:**
- Modify: `test/test_task_naming.py`
- Create: `backend/scripts/add_task_name_column.sql`
- Test: `test/test_task_naming.py`

**Step 1: Write the failing test**

在 `test/test_task_naming.py` 追加断言：

- `backend/scripts/add_task_name_column.sql` 文件存在
- 脚本包含 `ALTER TABLE tasks ADD COLUMN name`
- 脚本包含任务名索引创建语句

**Step 2: Run test to verify it fails**

Run: `pytest test/test_task_naming.py -v`
Expected: FAIL，因为脚本还不存在。

**Step 3: Write minimal implementation**

创建 `backend/scripts/add_task_name_column.sql`：

```sql
ALTER TABLE tasks ADD COLUMN name TEXT;
CREATE INDEX IF NOT EXISTS ix_tasks_name ON tasks(name);
```

可在文件头部注明：

- 适用于已存在 `tasks` 表的开发/部署库
- `create_all()` 不会自动补列

**Step 4: Run test to verify it passes**

Run: `pytest test/test_task_naming.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/scripts/add_task_name_column.sql test/test_task_naming.py
git commit -m "chore: add task name column migration script"
```

### Task 4: 为前端任务命名交互建立失败测试

**Files:**
- Create: `frontend/test/task-name-surface.test.ts`
- Test: `frontend/test/task-name-surface.test.ts`

**Step 1: Write the failing test**

在 `frontend/test/task-name-surface.test.ts` 中断言以下源码行为：

- `frontend/src/views/tools/Detail.vue` 包含任务名称输入框和“可选，留空将自动生成”文案
- `frontend/src/views/tools/Detail.vue` 调用 `tasksStore.createTask({... name: ... })`
- `frontend/src/components/workflow/WorkflowRunPanel.vue` 也包含任务名称输入逻辑，并把 `name` 传给 `createTask`
- `frontend/src/views/tasks/List.vue` 优先显示 `task.name`
- `frontend/src/views/tasks/Detail.vue` 主标题优先使用 `task.name`
- `frontend/src/types/models.d.ts` 中 `Task` 与 `TaskCreateParams` 包含 `name`

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/task-name-surface.test.ts"`
Expected: FAIL，因为前端还没有任务名字段和输入控件。

**Step 3: Commit**

```bash
git add frontend/test/task-name-surface.test.ts
git commit -m "test: add task naming frontend surface coverage"
```

### Task 5: 实现前端任务命名输入、展示与类型扩展

**Files:**
- Modify: `frontend/src/types/models.d.ts`
- Modify: `frontend/src/api/tasks.ts`
- Modify: `frontend/src/stores/tasks.ts`
- Modify: `frontend/src/views/tools/Detail.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Modify: `frontend/src/views/tasks/List.vue`
- Modify: `frontend/src/views/tasks/Detail.vue`
- Modify: `frontend/src/workflow/artifact-types.ts`
- Modify: `frontend/src/workflow/task-state.ts`
- Test: `frontend/test/task-name-surface.test.ts`

**Step 1: Write minimal implementation**

类型扩展：

```ts
export interface TaskCreateParams {
  name?: string
  tool_id: string
  ...
}
```

```ts
export interface Task {
  name?: string
  ...
}
```

工作台任务引用也补上：

```ts
| 'name'
```

单工具页 `frontend/src/views/tools/Detail.vue`：

- 新增 `const taskName = ref('')`
- 在参数表单顶部增加 `a-form-item`
- 提交时：

```ts
const normalizedTaskName = taskName.value.trim()
...
const task = await tasksStore.createTask({
  name: normalizedTaskName || undefined,
  tool_id: tool.value!.id,
  params: payload.params,
  file_ids: payload.fileIds.length > 0 ? payload.fileIds : undefined
})
```

工作台运行面板 `frontend/src/components/workflow/WorkflowRunPanel.vue` 做同样处理。

任务列表 `frontend/src/views/tasks/List.vue`：

- 主标题改成 `task.name || task.tool?.name || t('tasks.unknownTool')`
- 次级信息保留工具名和 `id`

任务详情 `frontend/src/views/tasks/Detail.vue`：

- 新增 `const taskTitle = computed(() => task.value?.name || task.value?.tool?.name || taskId.value)`
- 页面主标题和主要标题区改为使用 `taskTitle`

**Step 2: Run test to verify it passes**

Run: `node --test "frontend/test/task-name-surface.test.ts"`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/types/models.d.ts frontend/src/api/tasks.ts frontend/src/stores/tasks.ts frontend/src/views/tools/Detail.vue frontend/src/components/workflow/WorkflowRunPanel.vue frontend/src/views/tasks/List.vue frontend/src/views/tasks/Detail.vue frontend/src/workflow/artifact-types.ts frontend/src/workflow/task-state.ts frontend/test/task-name-surface.test.ts
git commit -m "feat: add task naming to frontend task creation and views"
```

### Task 6: 运行回归验证并检查构建

**Files:**
- Test: `test/test_task_naming.py`
- Test: `frontend/test/task-name-surface.test.ts`

**Step 1: Run backend targeted tests**

Run: `pytest test/test_task_naming.py -v`
Expected: PASS

**Step 2: Run existing task-related backend regression**

Run: `pytest test/test_task_direct_execution.py -q`
Expected: PASS

**Step 3: Run frontend targeted tests**

Run: `node --test "frontend/test/task-name-surface.test.ts"`
Expected: PASS

**Step 4: Run frontend build**

Run: `npm run build`
Workdir: `frontend`
Expected: PASS

**Step 5: Commit verification-only follow-up if needed**

```bash
git add .
git commit -m "test: verify task naming rollout"
```

Plan complete and saved to `docs/plans/2026-05-30-task-naming.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
