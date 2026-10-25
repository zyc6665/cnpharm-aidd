# Frontend Domain Extraction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 Vue 页面中的业务规则逐批抽成框架无关 TypeScript 深模块，先从任务中心开始。

**Architecture:** Vue 保留为 UI Adapter；业务规则进入 `frontend/src/domain/*` 和现有 `frontend/src/workflow/*`。domain 模块只接收普通对象并返回普通值，不依赖 Vue、Pinia、router 或 Ant Design Vue。

**Tech Stack:** Vue 3, Vite, TypeScript, Vitest, Pinia, Ant Design Vue.

---

### Task 1: Task Domain Test Surface

**Files:**
- Create: `frontend/src/domain/tasks/status.spec.ts`
- Create: `frontend/src/domain/tasks/listing.spec.ts`
- Create: `frontend/src/domain/tasks/permissions.spec.ts`
- Create: `frontend/src/domain/tasks/navigation.spec.ts`

**Step 1: Write failing tests**

Add tests for these behaviors:

```ts
// status.spec.ts
getTaskStatusColor('running') === 'processing'
getTaskProgressStatus('failure') === 'exception'
getTaskProgressColor('success') === '#52c41a'

// listing.spec.ts
filterTasksForTab(tasks, 'running') returns pending/running
filterTasksForTab(tasks, 'history') returns success/failure/canceled
filterTasksByKeyword(tasks, 'dock') checks name/tool/tool_name/id
paginateTasks(tasks, 2, 2) returns second page

// permissions.spec.ts
admin can operate any task
task owner can operate own task
project owner/editor/runner can operate project task
viewer cannot cancel/retry project task
delete remains admin-only and terminal-status-only

// navigation.spec.ts
getTaskProjectContextLabel uses project name when available
getTaskProjectContextLabel falls back to short project id
getTaskArtifactLineagePath returns project lineage path or workspace
```

**Step 2: Run tests to verify failure**

Run:

```bash
cd frontend && npm run test -- src/domain/tasks/status.spec.ts src/domain/tasks/listing.spec.ts src/domain/tasks/permissions.spec.ts src/domain/tasks/navigation.spec.ts
```

Expected: FAIL because `frontend/src/domain/tasks/*` modules do not exist.

### Task 2: Task Domain Implementation

**Files:**
- Create: `frontend/src/domain/tasks/status.ts`
- Create: `frontend/src/domain/tasks/listing.ts`
- Create: `frontend/src/domain/tasks/permissions.ts`
- Create: `frontend/src/domain/tasks/navigation.ts`
- Create: `frontend/src/domain/tasks/index.ts`

**Step 1: Implement pure functions**

Implement the functions covered by Task 1. Keep inputs as plain TypeScript objects:

```ts
type TaskActor = {
  isAdmin: boolean
  userId?: string
  projectId?: string
  projectRole?: ProjectRole
}

type TaskProjectContext = {
  currentProjectId?: string
  currentProjectName?: string
}
```

**Step 2: Run domain tests**

Run:

```bash
cd frontend && npm run test -- src/domain/tasks/status.spec.ts src/domain/tasks/listing.spec.ts src/domain/tasks/permissions.spec.ts src/domain/tasks/navigation.spec.ts
```

Expected: PASS.

### Task 3: Wire Task List Page To Domain

**Files:**
- Modify: `frontend/src/views/tasks/List.vue`
- Modify: `frontend/test/task-list-project-permissions.test.ts`
- Modify: `frontend/test/project-task-filter.test.ts`

**Step 1: Replace inline rules**

Import from `@/domain/tasks` and replace inline implementations for:

- status color/progress helpers
- running/history filtering
- keyword filtering
- pagination
- can operate/cancel/retry/delete
- project context label
- artifact lineage path

Keep `getStatusText()` in the Vue page because it uses `vue-i18n`.

**Step 2: Update source-level regression tests**

Update existing source tests to assert `List.vue` imports `@/domain/tasks` and no longer owns the core permission/listing logic.

**Step 3: Run focused tests**

Run:

```bash
cd frontend && npm run test -- src/domain/tasks/status.spec.ts src/domain/tasks/listing.spec.ts src/domain/tasks/permissions.spec.ts src/domain/tasks/navigation.spec.ts test/task-list-project-permissions.test.ts test/project-task-filter.test.ts test/task-list-card-accessibility.test.ts test/task-detail-progress-actions.test.ts
```

Expected: PASS.

### Task 4: Batch Verification And Commit

**Files:**
- Verify all files touched in Tasks 1-3.

**Step 1: Build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS, allowing existing Vite chunk/eval warnings.

**Step 2: Diff review**

Run:

```bash
git diff -- frontend/src/domain/tasks frontend/src/views/tasks/List.vue frontend/test/task-list-project-permissions.test.ts frontend/test/project-task-filter.test.ts
git diff --check
```

Expected: no whitespace errors; only task domain extraction changes.

**Step 3: Commit**

Run:

```bash
git add frontend/src/domain/tasks frontend/src/views/tasks/List.vue frontend/test/task-list-project-permissions.test.ts frontend/test/project-task-filter.test.ts
git commit -m "refactor(frontend): extract task domain rules"
```

Expected: commit created, unrelated docs changes remain unstaged.

### Task 5: Next Batches

After Task 4, continue with separate review + commit batches:

1. Extract Tool Package domain rules.
2. Extract Project Workspace domain rules.
3. Deepen existing Workflow domain modules.
