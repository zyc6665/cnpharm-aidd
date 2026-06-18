# Workflow Results Report Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a workflow-level results summary and Markdown report export so drug discovery users can review run outcomes and share reproducible notes.

**Architecture:** Build a frontend-only summary layer over existing workflow state, task refs, and artifacts. Keep task visualization components unchanged and add a dedicated workflow report component that derives summary rows and exports Markdown.

**Tech Stack:** Vue 3, Pinia, Ant Design Vue, Node test runner, Vite.

---

### Task 1: Report Surface Tests

**Files:**
- Modify: `frontend/test/workflow-template-page-surface.test.ts`
- Create: `frontend/test/workflow-results-report.test.ts`

**Step 1: Write failing page surface test**

Assert `frontend/src/views/workflow/index.vue` contains:
- `WorkflowResultsReportPanel`
- `workflow-results-region`
- `workflowReportRows`
- `exportWorkflowReportMarkdown`

**Step 2: Write failing report component test**

Assert `frontend/src/components/workflow/WorkflowResultsReportPanel.vue` exists and contains:
- `workflow-results-report-panel`
- `buildWorkflowReportMarkdown`
- `导出报告`
- `节点结果`
- `产物摘要`

**Step 3: Run tests**

Run:
```bash
cd frontend && node --test "test/workflow-template-page-surface.test.ts" "test/workflow-results-report.test.ts"
```

Expected: FAIL because component and page integration do not exist yet.

### Task 2: Report Component

**Files:**
- Create: `frontend/src/components/workflow/WorkflowResultsReportPanel.vue`
- Test: `frontend/test/workflow-results-report.test.ts`

**Step 1: Implement component props**

Accept:
- `workflowName: string`
- `nodes`
- `taskByNode`
- `artifacts`
- `nodeStatuses`

**Step 2: Implement summary rows**

Render:
- node title
- selected status
- task id/status
- matching artifact count

**Step 3: Implement Markdown export**

Add `buildWorkflowReportMarkdown` and a button that downloads `workflow-report.md`.

**Step 4: Verify**

Run:
```bash
cd frontend && node --test "test/workflow-results-report.test.ts"
```

Expected: PASS.

### Task 3: Workflow Page Integration

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/test/workflow-template-page-surface.test.ts`

**Step 1: Import panel**

Import `WorkflowResultsReportPanel`.

**Step 2: Add results region**

Render a `workflow-results-region` below the canvas layout.

**Step 3: Add computed rows**

Expose `workflowReportRows` based on current editable nodes, node statuses, task refs, and artifacts.

**Step 4: Verify**

Run:
```bash
cd frontend && node --test "test/workflow-template-page-surface.test.ts"
```

Expected: PASS.

### Task 4: Full Verification

**Files:**
- Test: `frontend/test/*.test.ts`

**Step 1: Run workflow regression tests**

Run:
```bash
cd frontend && node --test "test/workflow-template-state.test.ts" "test/workflow-node-run-binding.test.ts" "test/workflow-template-canvas-surface.test.ts" "test/workflow-template-page-surface.test.ts" "test/workflow-node-inspector-surface.test.ts" "test/workflow-canvas-drag-persistence.test.ts" "test/workflow-definitions-api-store.test.ts" "test/workflow-run-ready-nodes.test.ts" "test/task-agent-grouping.test.ts" "test/workflow-results-report.test.ts"
```

Expected: PASS.

**Step 2: Build**

Run:
```bash
cd frontend && npm run build
```

Expected: PASS with only existing Vite warnings.

**Step 3: Smoke test page**

Run:
```bash
curl -I "http://localhost:8591/workflow"
```

Expected: `200 OK`.
