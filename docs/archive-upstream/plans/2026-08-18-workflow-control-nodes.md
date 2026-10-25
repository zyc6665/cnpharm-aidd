# Workflow Control Nodes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expose existing backend workflow control-flow support in the frontend workflow canvas through condition, map, and loop nodes.

**Architecture:** Keep control nodes as first-class canvas nodes at the existing workflow canvas seam. The frontend serializes node-specific control fields into the workflow definition shape already supported by backend validation and scheduling.

**Tech Stack:** Vue 3, TypeScript, Pinia, Vitest, existing workflow canvas modules, existing backend workflow validation/scheduler contracts.

---

### Task 1: Canvas Type And Store Support

**Files:**
- Modify: `frontend/src/workflow/canvas-types.ts`
- Modify: `frontend/src/stores/workflow-canvas.ts`
- Test: `frontend/src/stores/__tests__/workflow-canvas.spec.ts`

**Step 1: Write the failing test**

Add a test proving the canvas store can add a control node and preserve its control config.

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- workflow-canvas.spec.ts`
Expected: FAIL because control node add helpers/types do not exist.

**Step 3: Write minimal implementation**

Extend node type support for `condition`, `map`, and `loop`, and add a small store method for creating control nodes.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- workflow-canvas.spec.ts`
Expected: PASS.

### Task 2: Workflow Definition Serialization

**Files:**
- Modify: `frontend/src/composables/useWorkflowCanvas.ts`
- Test: `frontend/src/composables/useWorkflowCanvas.spec.ts`

**Step 1: Write the failing test**

Add a test proving condition/map/loop canvas nodes serialize to backend-compatible `kind` and fields.

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- useWorkflowCanvas.spec.ts`
Expected: FAIL because all non-input nodes serialize as `tool`.

**Step 3: Write minimal implementation**

Serialize control node fields directly: condition `expression`, map `over/max_parallelism`, loop `body/max_iterations/convergence_condition`.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- useWorkflowCanvas.spec.ts`
Expected: PASS.

### Task 3: Page Controls

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/components/workflow/WorkflowCanvasBoard.vue`
- Modify: `frontend/src/components/workflow/WorkflowNodeInspector.vue`
- Test: focused frontend workflow tests if existing coverage targets the page; otherwise rely on composable/store tests plus build.

**Step 1: Add minimal UI**

Add buttons near the tool palette for condition/map/loop nodes and display them on the canvas with existing node rendering.

**Step 2: Verify**

Run: `cd frontend && npm run test -- workflow-canvas.spec.ts useWorkflowCanvas.spec.ts`
Run: `cd frontend && npm run build`
Expected: PASS.

### Task 4: Final Verification And Atomic Commit

**Files:**
- All files changed in Tasks 1-3.

**Step 1: Verify**

Run: `cd frontend && npm run test`
Run: `cd frontend && npm run build`
Run: `git diff --check`

**Step 2: Commit after confirmation**

Only after explicit user confirmation, commit the scoped changes.
