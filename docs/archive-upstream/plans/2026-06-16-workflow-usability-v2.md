# Workflow Usability V2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve the workflow page information architecture so users can find tools, understand readiness, configure nodes, manage dependencies, and inspect results without scanning one long panel.

**Architecture:** Keep the current Vue 3 page and Pinia store. Move tool discovery into the left sidebar, keep the canvas graph-only, and convert the node inspector into a tabbed panel without changing backend APIs.

**Tech Stack:** Vue 3, Pinia, Ant Design Vue, Vite, Node test runner.

---

### Task 1: Layout Surface Tests

**Files:**
- Modify: `frontend/test/workflow-template-page-surface.test.ts`
- Modify: `frontend/test/workflow-template-canvas-surface.test.ts`
- Modify: `frontend/test/workflow-node-inspector-surface.test.ts`

**Steps:**
1. Add failing tests for sidebar tool library markers.
2. Add failing tests for workflow run summary markers.
3. Add failing tests for inspector tabs.
4. Run the focused tests and confirm failures.

### Task 2: Sidebar Tool Library

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/components/workflow/WorkflowTemplateCanvas.vue`

**Steps:**
1. Move searchable tool list from the canvas into the left sidebar.
2. Remove tool-library UI from the canvas component.
3. Keep `add-tool-node` behavior unchanged.
4. Run focused page and canvas tests.

### Task 3: Run Summary and Status Reasons

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`

**Steps:**
1. Add computed counts for ready, blocked, running, completed, and failed nodes.
2. Add `resolveNodeStatusReason` for node list labels.
3. Render the summary as compact operational chips.
4. Run focused page tests.

### Task 4: Tabbed Inspector

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowNodeInspector.vue`

**Steps:**
1. Wrap configuration, dependencies, and results in Ant Design tabs.
2. Keep node run panel in the configuration tab.
3. Keep edge editing and semantic IO in the dependencies tab.
4. Keep task result in the results tab.
5. Run focused inspector tests.

### Task 5: Verification

**Files:**
- Test: `frontend/test/*.test.ts`

**Steps:**
1. Run workflow-focused Node tests.
2. Run `npm run build`.
3. Confirm `/workflow` returns 200.
