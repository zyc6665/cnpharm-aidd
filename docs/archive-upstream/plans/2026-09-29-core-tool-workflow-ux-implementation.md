# Core Tool and Workflow UX Implementation Plan

> **For Codex:** Implement the approved design in small, scoped changes. Preserve all unrelated worktree changes and do not commit.

**Goal:** Close the broken or misleading tool and workflow paths identified in the UX review.

**Architecture:** Keep Task and WorkflowRun semantics separate. Route project ArtifactVersion inputs through existing workflow node Run Preparation, extend the runtime form for the schema types registration accepts, and keep destructive workflow edits guarded at the persistence interface.

**Tech Stack:** Vue 3, TypeScript, Ant Design Vue, FastAPI, SQLAlchemy.

---

### Task 1: Align workflow run actions

**Files:**
- Modify `frontend/src/components/workflow/WorkflowCanvasPanelNode.vue`
- Modify `frontend/src/components/workflow/WorkflowCanvasBoard.vue`
- Modify `frontend/src/components/workflow/WorkflowNodeInspector.vue`
- Modify `frontend/src/components/workflow/NodeResultPanel.vue`
- Modify `frontend/src/views/workflow/index.vue`
- Modify `frontend/src/composables/useWorkflowPersistence.ts`
- Modify `frontend/src/locales/zh-CN/index.ts`
- Modify `frontend/src/locales/en-US/index.ts`

**Work:** Replace the unhandled canvas run event with an action that selects the node and opens its configuration. Keep standalone node execution on the parameter form. Make full workflow execution labels describe a new full run and ensure preflight does not describe it as a partial node run.

### Task 2: Add project Artifact and upload inputs to workflows

**Files:**
- Modify `frontend/src/components/workflow/WorkflowRunInputPanel.vue`
- Modify `frontend/src/views/workflow/index.vue`
- Modify `frontend/src/composables/useWorkflowPersistence.ts`
- Modify `frontend/src/api/artifacts.ts`
- Modify `backend/app/services/workflow_inputs.py`
- Modify `backend/app/services/workflow_run_input_sources.py`
- Modify `backend/app/services/workflow_runs.py`
- Modify `backend/app/schemas/workflows.py`

**Work:** Project workflow inputs use compatible project Typed Artifacts and support uploading a typed input. Non-project workflows retain reusable Task output files and gain direct upload. Validate ArtifactVersion ownership, project scope, semantic type, availability, and expiry before resolving its files for task preparation.

### Task 3: Render all registered parameter types

**Files:**
- Modify `frontend/src/components/tools/ToolParameterForm.vue`
- Modify `frontend/src/components/workflow/WorkflowNodeRunPanel.vue`

**Work:** Add email/URL string inputs and JSON editors for object and non-enum array values. Keep parse errors visible and prevent invalid JSON from being submitted.

### Task 4: Configure Workflow control nodes

**Files:**
- Modify `frontend/src/components/workflow/NodeToolPanel.vue`
- Modify `frontend/src/components/workflow/NodeEdgePanel.vue`
- Modify `frontend/src/components/workflow/WorkflowNodeInspector.vue`
- Modify `frontend/src/workflow/canvas-types.ts`
- Modify `frontend/src/workflow/canvas-presets.ts`
- Modify `frontend/src/composables/useWorkflowCanvas.ts`
- Modify `frontend/src/composables/useWorkflowPersistence.ts`
- Modify `frontend/src/stores/workflow-canvas.ts`
- Modify `frontend/src/stores/workflow.ts`

**Work:** Edit Map source and parallelism, edit condition operator and operands, select true/false branch metadata for condition edges, and preserve those fields through save/load.

### Task 5: Protect unsaved workflow edits and validate node runs

**Files:**
- Modify `frontend/src/composables/useWorkflowPersistence.ts`
- Modify `frontend/src/views/workflow/index.vue`
- Modify `frontend/src/components/workflow/WorkflowNodeRunPanel.vue`

**Work:** Track a saved workflow snapshot and confirm before replacing dirty edits. Validate node form fields before creating a Task and display validation errors next to the relevant fields.

### Task 6: Verify

Run `npm run build` in `frontend`, `python -m compileall backend/app`, and `git diff --check`. Test suites are not added or run in this task.
