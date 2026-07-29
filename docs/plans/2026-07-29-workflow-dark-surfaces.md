# Workflow Dark Surface Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove hard-coded neutral light surfaces from all workflow components.

**Architecture:** Keep the existing dark-first theme system unchanged. Map top-level panels to
`@bg-surface`, nested elements to `@bg-elevated`, and neutral borders to the existing theme border
tokens. Protect the whole workflow component directory with a source-level regression test.

**Tech Stack:** Vue 3 single-file components, Less theme variables, Vitest, Node assertions.

---

### Task 1: Add the Inspector Theme Regression

**Files:**
- Modify: `frontend/test/workflow-node-inspector-surface.test.ts`

**Step 1: Write the failing test**

Add a test that reads `WorkflowNodeInspector.vue`, `WorkflowNodeRunPanel.vue`, and
`WorkflowNodeStatusBadge.vue`. Assert that none contains `rgba(255, 255, 255` and that both child
components contain `background: @bg-elevated`.

**Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- test/workflow-node-inspector-surface.test.ts`

Expected: FAIL because both child components still contain translucent white backgrounds.

### Task 2: Use Semantic Theme Surfaces

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowNodeRunPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowNodeStatusBadge.vue`
- Test: `frontend/test/workflow-node-inspector-surface.test.ts`

**Step 1: Implement the minimum style change**

Replace each neutral `rgba(255, 255, 255, ...)` background with:

```less
background: @bg-elevated;
```

Do not change status colors, borders, layout, typography, or interactions.

### Task 3: Cover All Workflow Theme Surfaces

**Files:**
- Create: `frontend/test/workflow-theme-surfaces.test.ts`
- Modify: `frontend/src/components/workflow/AiddAgentPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowArtifactPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowCanvasEdge.vue`
- Modify: `frontend/src/components/workflow/WorkflowCanvasNode.vue`
- Modify: `frontend/src/components/workflow/WorkflowResultsReportPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunHistoryPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunInputPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowRunStatusPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowStepSidebar.vue`
- Modify: `frontend/src/components/workflow/WorkflowTaskResultPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowTemplateCanvas.vue`
- Modify: `frontend/src/components/workflow/WorkflowTemplateToolbar.vue`
- Modify: `frontend/src/components/workflow/WorkflowToolPalette.vue`

**Step 1: Write the failing directory-level test**

Read every `.vue` file under `src/components/workflow`. Reject the audited neutral white,
near-white, and light-only border values. Assert representative top-level panels contain
`@bg-surface` and representative nested elements contain `@bg-elevated`.

**Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- test/workflow-theme-surfaces.test.ts`

Expected: FAIL with the first remaining light-only value and component filename.

**Step 3: Implement the semantic token mapping**

Replace top-level backgrounds and borders with `@bg-surface` and `@border-color-hover`. Replace
nested backgrounds and borders with `@bg-elevated` and `@border-color`. Preserve status colors,
accent states, layout, typography, and interactions.

**Step 4: Run focused tests**

Run: `cd frontend && npm run test -- test/workflow-theme-surfaces.test.ts test/workflow-node-inspector-surface.test.ts test/workflow-preflight-panel.test.ts test/workflow-template-canvas-surface.test.ts test/workflow-persistence-surface.test.ts test/workflow-results-report.test.ts`

Expected: all focused tests PASS.

**Step 5: Run full verification**

Run: `cd frontend && npm run test`

Expected: all frontend tests PASS.

Run: `cd frontend && npm run build`

Expected: type checking and the Vite production build PASS.

**Step 6: Commit**

```bash
git add frontend/test/workflow-node-inspector-surface.test.ts \
  frontend/test/workflow-theme-surfaces.test.ts \
  frontend/src/components/workflow
git commit -m "fix(frontend): theme workflow inspector surfaces"
```
