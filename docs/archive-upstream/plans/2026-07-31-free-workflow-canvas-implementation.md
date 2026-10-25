# Free Workflow Canvas Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert the tool workbench from fixed template selection to a free, user-built process canvas while keeping saved process and run compatibility.

**Architecture:** The frontend should use `WorkflowDefinition` as the primary "流程" model and keep legacy `WorkflowTemplate` APIs only as compatibility sources. The canvas state should default to an empty graph and use the existing canvas store for node, edge, position, and run state. Execution remains node-first with preflight validation.

**Tech Stack:** Vue 3, Pinia, TypeScript, Ant Design Vue, Vitest, FastAPI workflow APIs.

---

### Task 1: Lock Free-Canvas Defaults

**Files:**
- Modify: `frontend/src/stores/workflow-session-store.ts`
- Modify: `frontend/src/composables/useWorkflowCanvas.ts`
- Test: `frontend/src/stores/__tests__/workflow-canvas.spec.ts`

**Step 1: Write failing tests**

Add tests proving a new workflow session starts with an empty canvas and does not fall back to built-in template nodes when the user deletes all nodes.

**Step 2: Run tests to verify failure**

Run: `cd frontend && npm test -- src/stores/__tests__/workflow-canvas.spec.ts --run`

Expected: FAIL before implementation because the page still derives from built-in templates.

**Step 3: Implement minimal state change**

Keep `hasCanvasOverride` as the source of truth, default sessions to a neutral `free-canvas` template id, and ensure `editableTemplate` can represent an empty flow.

**Step 4: Verify**

Run the same Vitest command. Expected: PASS.

### Task 2: Remove User-Visible Template UI

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/composables/useWorkflowPersistence.ts`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`
- Test: create `frontend/src/views/workflow/free-workflow.spec.ts`

**Step 1: Write failing UI tests**

Mount the workflow view and assert it shows flow language (`流程`) and does not render template selector or template toolbar labels.

**Step 2: Run tests to verify failure**

Run: `cd frontend && npm test -- src/views/workflow/free-workflow.spec.ts --run`

Expected: FAIL because current UI still renders "模板选择" and `WorkflowTemplateToolbar`.

**Step 3: Implement minimal UI change**

Remove `WorkflowTemplateToolbar`, the built-in template selector, and template options from the manual tab. Keep the existing save/load flow bar and rename copy to "流程".

**Step 4: Verify**

Run the same Vitest command. Expected: PASS.

### Task 3: Preserve Save/Load/Run Compatibility

**Files:**
- Modify: `frontend/src/composables/useWorkflowPersistence.ts`
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/src/views/workflow/free-workflow.spec.ts`

**Step 1: Write failing tests**

Assert saving a free flow writes `template_id: "free-canvas"`, loading applies stored nodes/edges, and run history remains visible.

**Step 2: Run tests to verify failure**

Run: `cd frontend && npm test -- src/views/workflow/free-workflow.spec.ts --run`

Expected: FAIL before persistence cleanup.

**Step 3: Implement compatibility facade**

Route new save/load through `WorkflowDefinition`; leave legacy template API calls out of the UI. Keep run history calls unfiltered unless a run is selected.

**Step 4: Verify**

Run the same Vitest command. Expected: PASS.

### Task 4: Production Verification

**Files:**
- Verify: frontend tests and build

**Step 1: Run focused tests**

Run: `cd frontend && npm test -- src/views/workflow/free-workflow.spec.ts src/stores/__tests__/workflow-canvas.spec.ts --run`

**Step 2: Run production build**

Run: `cd frontend && npm run build`

**Step 3: Report**

Report exact commands, pass/fail status, and any remaining warnings. Do not commit unless explicitly requested.
