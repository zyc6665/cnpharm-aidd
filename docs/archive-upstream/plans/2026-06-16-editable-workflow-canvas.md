# Editable Workflow Canvas Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the workflow canvas usable with real tool nodes, node deletion, basic edge editing, save/load, and one-click running.

**Architecture:** Keep the current Vue/Pinia implementation and promote editable nodes/edges into `useWorkflowStore`. The template remains the initial graph; edited state becomes the source of truth for canvas rendering, save payloads, status calculation, and running.

**Tech Stack:** Vue 3, Pinia, Ant Design Vue, Node test runner, TypeScript, existing FastAPI workflow persistence endpoints.

---

### Task 1: Store Editable Graph State

**Files:**
- Modify: `frontend/src/stores/workflow.ts`
- Test: `frontend/test/workflow-editable-canvas-state.test.ts`

**Steps:**
1. Add failing tests for `ensureCanvasFromTemplate`, `addToolNode`, `deleteCanvasNode`, and `addCanvasEdge`.
2. Add `canvasNodes` and `canvasEdges` to the persisted workflow store.
3. Implement add/delete/edge actions and cleanup related node state.
4. Run `node --test test/workflow-editable-canvas-state.test.ts`.

### Task 2: Real Tool Options

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowNodeInspector.vue`
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/test/workflow-node-inspector-surface.test.ts`

**Steps:**
1. Add failing tests that inspector accepts `availableTools` and no longer only maps `node.toolSlugs`.
2. Pass flattened tools from `toolsStore.workbenchGroups` and `toolsStore.workflowToolOptions`.
3. Use real tool names in the selector and emit selected slugs.
4. Load both workbench groups and workflow tool options on mount.

### Task 3: Add/Delete Nodes

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowTemplateCanvas.vue`
- Modify: `frontend/src/components/workflow/WorkflowCanvasNode.vue`
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/test/workflow-canvas-drag-persistence.test.ts`

**Steps:**
1. Add failing tests for add-tool control, delete-node emit, and page wiring.
2. Add a toolbar selector/button for adding tool nodes.
3. Add a small delete button on editable tool nodes.
4. Wire page handlers to workflow store actions.

### Task 4: Basic Edge Editing

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowNodeInspector.vue`
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/test/workflow-node-inspector-surface.test.ts`

**Steps:**
1. Add failing tests for upstream edge controls and `add-edge` emit.
2. Add source-node and artifact-type selectors in the inspector.
3. Wire page handler to `workflowStore.addCanvasEdge`.
4. Ensure statuses use edited edges.

### Task 5: Save/Load/Run Edited Graph

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/stores/workflow.ts`
- Test: `frontend/test/workflow-run-ready-nodes.test.ts`
- Test: `frontend/test/workflow-definitions-api-store.test.ts`

**Steps:**
1. Add failing tests that save uses edited graph and run reads edited graph.
2. Update payload creation to use `workflowStore.canvasNodes` and `workflowStore.canvasEdges`.
3. Update loading to restore editable graph.
4. Run all workflow-related tests and `npm run build`.
