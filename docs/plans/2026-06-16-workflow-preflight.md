# Workflow Preflight Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a visible run-readiness check to the workflow canvas page.

**Architecture:** Implement reusable preflight logic as a pure TypeScript helper, then render it with a small Vue component mounted in `frontend/src/views/workflow/index.vue`.

**Tech Stack:** Vue 3, TypeScript, Ant Design Vue, Node test runner.

---

### Task 1: Preflight Helper

**Files:**
- Create: `frontend/src/workflow/preflight.ts`
- Test: `frontend/test/workflow-preflight.test.ts`

**Steps:**
1. Write a failing test for runnable counts and blocking issues.
2. Run `node --test "test/workflow-preflight.test.ts"` and confirm missing module failure.
3. Implement `buildWorkflowPreflight`.
4. Re-run the test and confirm it passes.

### Task 2: Preflight Panel

**Files:**
- Create: `frontend/src/components/workflow/WorkflowPreflightPanel.vue`
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/test/workflow-preflight-panel.test.ts`

**Steps:**
1. Write failing surface tests for the panel and page integration.
2. Add the Vue component with summary, issues, and run action.
3. Mount the panel above the canvas and wire events to existing handlers.
4. Run `node --test "test/workflow-preflight.test.ts" "test/workflow-preflight-panel.test.ts"`.

### Task 3: Verification

**Steps:**
1. Run the focused workflow test set.
2. Run `npm run build`.
3. Confirm `/workflow` still serves from the dev server when available.
