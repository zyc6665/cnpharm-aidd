# Admin Backend Real API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove simulated admin-console features and wire the dashboard, users, tasks, tools, and system pages to real APIs.

**Architecture:** Keep the current admin route structure and page components, but replace mocked page state with API-driven loading. Prefer existing backend endpoints; only add minimal backend query support when a page is not usable without it.

**Tech Stack:** Vue 3, TypeScript, Ant Design Vue, Axios, FastAPI, pytest, Node test runner

---

### Task 1: Add admin surface regression tests

**Files:**
- Create: `frontend/test/admin-real-api-surface.test.ts`
- Test: `frontend/test/admin-real-api-surface.test.ts`

**Step 1: Write the failing test**

Add assertions that:

- `frontend/src/views/admin/Dashboard.vue` no longer contains `taskTrend` or `systemStatus`
- `frontend/src/views/admin/System.vue` no longer contains `handleSaveGeneral`, `handleSaveTasks`, `handleTestStorage`, `handleTestEmail`
- `frontend/src/views/admin/Users.vue` no longer contains `createUser` or `resetPassword`
- `frontend/src/views/admin/Tasks.vue` no longer contains `handleBatchCancel` or `handleBatchDelete`

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/admin-real-api-surface.test.ts"`
Expected: FAIL because current files still contain mocked admin features.

**Step 3: Write minimal implementation**

Do not change production code yet; only ensure the test encodes the new surface contract.

**Step 4: Run test to verify it still fails correctly**

Run: `node --test "frontend/test/admin-real-api-surface.test.ts"`
Expected: FAIL for the intended missing-removal assertions.

### Task 2: Add missing admin API wrappers and align response types

**Files:**
- Modify: `frontend/src/api/users.ts`
- Modify: `frontend/src/api/system.ts`
- Modify: `frontend/src/types/models.d.ts`
- Test: `frontend/test/admin-real-api-surface.test.ts`

**Step 1: Write the failing test**

Extend the surface test to assert that:

- `frontend/src/api/users.ts` exports admin list/stats/update/delete helpers
- `frontend/src/api/system.ts` uses typed `SystemInfo` / `SystemStats` / `SystemConfig`

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/admin-real-api-surface.test.ts"`
Expected: FAIL because these wrappers and types do not exist yet.

**Step 3: Write minimal implementation**

- Add admin user API wrappers for list, stats, patch, delete
- Align `SystemHealth`, `SystemStats`, and add `SystemInfo` / `SystemConfig` types to match backend payloads closely enough for UI use

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/admin-real-api-surface.test.ts"`
Expected: PASS for API/type assertions

### Task 3: Refactor Dashboard to real summary data

**Files:**
- Modify: `frontend/src/views/admin/Dashboard.vue`
- Test: `frontend/test/admin-real-api-surface.test.ts`

**Step 1: Write the failing test**

Add assertions that `Dashboard.vue` imports and uses:

- admin user stats API
- system stats API
- task list API
- admin user list API

And assert removed mocked sections stay absent.

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/admin-real-api-surface.test.ts"`
Expected: FAIL because dashboard still uses mocked state.

**Step 3: Write minimal implementation**

- Replace mocked `stats`, `recentTasks`, and `recentUsers` with async loading
- Remove chart/system-status code
- Keep layout simple: summary cards + recent task/user tables

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/admin-real-api-surface.test.ts"`
Expected: PASS

### Task 4: Refactor Users page to real admin user management

**Files:**
- Modify: `frontend/src/views/admin/Users.vue`
- Test: `frontend/test/admin-real-api-surface.test.ts`

**Step 1: Write the failing test**

Add assertions that `Users.vue` imports the admin user APIs and no longer contains create/reset-password UI text or handlers.

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/admin-real-api-surface.test.ts"`
Expected: FAIL because page is still backed by local mock arrays.

**Step 3: Write minimal implementation**

- Load stats and paginated users from the backend
- Wire filters and pagination to backend params
- Keep only edit and delete actions supported by real APIs

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/admin-real-api-surface.test.ts"`
Expected: PASS

### Task 5: Refactor Tasks page to real task operations

**Files:**
- Modify: `frontend/src/views/admin/Tasks.vue`
- Modify: `frontend/src/api/tasks.ts` (only if query params need extension)
- Test: `frontend/test/admin-real-api-surface.test.ts`

**Step 1: Write the failing test**

Add assertions that `Tasks.vue` imports real task APIs, removes hard-coded tool options, and removes batch action handlers.

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/admin-real-api-surface.test.ts"`
Expected: FAIL because page still uses mocked tasks.

**Step 3: Write minimal implementation**

- Load task list from backend with status/tool filters and pagination
- Load detail lazily from `getTaskDetail`
- Wire cancel/retry/delete to real endpoints
- Remove batch action UI

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/admin-real-api-surface.test.ts"`
Expected: PASS

### Task 6: Refactor Tools and System pages to real-only behavior

**Files:**
- Modify: `frontend/src/views/admin/Tools.vue`
- Modify: `frontend/src/views/admin/System.vue`
- Test: `frontend/test/admin-real-api-surface.test.ts`

**Step 1: Write the failing test**

Add assertions that:

- `Tools.vue` forwards filter params to `getToolList`
- `System.vue` imports `getSystemInfo`, `getSystemStats`, `getSystemConfig`
- `System.vue` no longer contains save/test handlers

**Step 2: Run test to verify it fails**

Run: `node --test "frontend/test/admin-real-api-surface.test.ts"`
Expected: FAIL because tools/system are not fully aligned yet.

**Step 3: Write minimal implementation**

- Update tools fetch logic to use real filter params and server results where available
- Replace system settings tabs with a read-only info/config presentation

**Step 4: Run test to verify it passes**

Run: `node --test "frontend/test/admin-real-api-surface.test.ts"`
Expected: PASS

### Task 7: Verify end-to-end surface and build health

**Files:**
- Test: `frontend/test/admin-real-api-surface.test.ts`
- Test: `frontend/test/admin-layout.test.ts`
- Test: `test/test_admin_tool_category_frontend_surface.py`

**Step 1: Run focused frontend surface tests**

Run: `node --test "frontend/test/admin-real-api-surface.test.ts" "frontend/test/admin-layout.test.ts"`
Expected: PASS

**Step 2: Run related Python surface tests**

Run: `pytest "test/test_admin_tool_category_frontend_surface.py" -v`
Expected: PASS

**Step 3: Run frontend build**

Run: `npm run build`
Workdir: `frontend`
Expected: PASS

**Step 4: Review output**

Confirm admin pages no longer depend on mocked sections and the build still succeeds.
