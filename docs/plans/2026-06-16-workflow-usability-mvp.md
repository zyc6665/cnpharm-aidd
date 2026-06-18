# Workflow Usability MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the workflow page usable for real tool execution, not just visual node placement.

**Architecture:** Reuse the existing tool execution path instead of creating a second parameter system. The canvas owns graph editing, the inspector owns node configuration, and the page orchestrates save/load plus dependency-aware execution.

**Tech Stack:** Vue 3, Pinia, Ant Design Vue, Vite, Node test runner, FastAPI task APIs.

---

### Task 1: Node Tool Library

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowTemplateCanvas.vue`
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/test/workflow-template-canvas-surface.test.ts`

**Steps:**
1. Add failing tests for a searchable node library with grouped tools.
2. Render available tools as a side drawer/dropdown surface with search.
3. Emit `add-tool-node` with the selected real tool slug.
4. Verify the canvas tests pass.

### Task 2: Node Run Panel

**Files:**
- Create: `frontend/src/components/workflow/WorkflowNodeRunPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowNodeInspector.vue`
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/test/workflow-node-inspector-surface.test.ts`

**Steps:**
1. Add failing tests that require schema form rendering, file/artifact selection, task submission, and polling markers.
2. Build `WorkflowNodeRunPanel` by reusing the existing `WorkflowRunPanel` form patterns.
3. Store drafts by node id and record tasks by node id.
4. Verify the inspector tests pass.

### Task 3: Graph Maintenance

**Files:**
- Modify: `frontend/src/stores/workflow.ts`
- Modify: `frontend/src/components/workflow/WorkflowNodeInspector.vue`
- Test: `frontend/test/workflow-canvas-drag-persistence.test.ts`

**Steps:**
1. Add failing tests for edge deletion and node IO metadata updates.
2. Allow deleting upstream edges from the inspector.
3. Derive added node required/produced types from selected edge/output metadata when available.
4. Verify persistence tests pass.

### Task 4: Dependency-Aware Full Run

**Files:**
- Modify: `frontend/src/workflow/template-runner.ts`
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/test/workflow-run-ready-nodes.test.ts`

**Steps:**
1. Add failing tests for topological ready-node ordering and repeated run progression.
2. Implement `resolveWorkflowExecutionOrder` and use it for one-click execution.
3. Poll each submitted task until terminal status before advancing downstream nodes.
4. Verify workflow runner tests and frontend build pass.
