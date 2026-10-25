# Admin Remote Recovery Filter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow administrators to filter the task list to tasks with Remote API recovery alerts.

**Architecture:** Reuse the existing task query pipeline. Add one optional query field to `TaskQueryInput`, apply a JSON boolean predicate against `Task.extra_data`, expose the field through the existing task list API, and bind a single select control in the administrator task page. No schema migration or new persistence model is needed.

**Tech Stack:** FastAPI, SQLAlchemy async queries, Vue 3, TypeScript, Vitest, pytest.

---

### Task 1: Add the failing backend contract test

**Files:**
- Modify: `test/test_task_detail_visualization.py`

**Step 1:** Seed one task with `remote_recovery_alerted=true` and one without it.

**Step 2:** Request `/api/v1/tasks?remote_recovery_alerted=true`.

**Step 3:** Assert only the alerted task is returned.

### Task 2: Add the failing frontend surface test

**Files:**
- Create: `frontend/test/admin-task-recovery-filter-surface.test.ts`

**Step 1:** Assert the administrator task view exposes the recovery filter, forwards the query field, and resets it.

### Task 3: Implement the backend filter

**Files:**
- Modify: `backend/app/services/task_views.py`
- Modify: `backend/app/api/v1/tasks.py`
- Modify: `frontend/src/api/tasks.ts`

**Step 1:** Add the optional boolean to the query dataclass and route.

**Step 2:** Apply the JSON boolean predicate only when the value is true.

### Task 4: Implement the administrator control

**Files:**
- Modify: `frontend/src/views/admin/Tasks.vue`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`

**Step 1:** Add a select option for tasks with recovery alerts.

**Step 2:** Include the field in fetch and reset it with other filters.

### Task 5: Verify the change

**Step 1:** Run the focused backend test.

**Step 2:** Run the focused frontend test.

**Step 3:** Run the full backend and frontend suites plus the frontend build.

No commit is planned until the user explicitly requests one.
