# Task JSON Result Renderer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a reusable renderer that displays structured task `output_data` as readable grouped lists instead of raw JSON blocks.

**Architecture:** Put formatting and classification logic in a pure TypeScript helper so it can be tested without mounting Vue. Use a small recursive Vue component for display, then wire it into `TaskOutputSummary.vue` while leaving output file downloads unchanged.

**Tech Stack:** Vue 3 `<script setup>`, TypeScript, Ant Design Vue, Node test runner with `tsx`.

---

### Task 1: Add Failing Tests For Generic JSON Result Rendering

**Files:**
- Create: `frontend/test/task-json-result-renderer.test.ts`
- Test target: `frontend/src/components/tasks/json-result-renderer.ts`
- Inspect: `frontend/src/components/tasks/TaskOutputSummary.vue`

**Step 1: Write failing tests**

Create tests that import `formatJsonResultLabel`, `formatJsonResultValue`, and `buildJsonResultEntries`. Include an MSIGN-like object with `prediction`, `preprocessing`, `metrics`, and `artifacts`.

**Step 2: Run the focused test**

Run: `cd frontend && npx tsx --test test/task-json-result-renderer.test.ts`

Expected: FAIL because `json-result-renderer.ts` does not exist.

### Task 2: Implement Pure Formatting Helpers

**Files:**
- Create: `frontend/src/components/tasks/json-result-renderer.ts`

**Step 1: Implement helpers**

Add:

- `formatJsonResultLabel(key: string): string`
- `formatJsonResultValue(value: unknown): string`
- `buildJsonResultEntries(value: unknown): JsonResultEntry[]`
- `isJsonRecord(value: unknown): value is Record<string, unknown>`

**Step 2: Run focused tests**

Run: `cd frontend && npx tsx --test test/task-json-result-renderer.test.ts`

Expected: PASS for helper behavior, still failing for Vue source integration assertions.

### Task 3: Add Recursive Vue Renderer

**Files:**
- Create: `frontend/src/components/tasks/JsonResultRenderer.vue`
- Modify: `frontend/src/components/tasks/TaskOutputSummary.vue`

**Step 1: Implement component**

Render sections, rows, arrays, empty values, and raw JSON fallback using stable classes such as `json-result-renderer`, `json-result-section`, and `json-result-raw`.

**Step 2: Wire component**

Replace object `JSON.stringify` display in `TaskOutputSummary.vue` with `<JsonResultRenderer :value="outputData" />`.

**Step 3: Run focused tests**

Run: `cd frontend && npx tsx --test test/task-json-result-renderer.test.ts`

Expected: PASS.

### Task 4: Verify Existing Task Result Surface

**Files:**
- Test: `frontend/test/workflow-inline-results.test.ts`
- Test: `frontend/test/task-result-visualization.test.ts`

**Step 1: Run adjacent tests**

Run:

```bash
cd frontend && npx tsx --test test/task-json-result-renderer.test.ts test/workflow-inline-results.test.ts test/task-result-visualization.test.ts
```

Expected: PASS.

**Step 2: Build type check**

Run: `cd frontend && npm run build`

Expected: PASS.
