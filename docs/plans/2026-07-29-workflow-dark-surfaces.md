# Workflow Dark Surface Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the remaining hard-coded translucent white surfaces from the split workflow
inspector components.

**Architecture:** Keep the existing dark-first theme system unchanged. Replace the two neutral
white backgrounds with the existing `@bg-elevated` runtime theme token and protect the inspector
surface with a source-level regression test consistent with the current frontend test suite.

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

**Step 2: Run focused tests**

Run: `cd frontend && npm run test -- test/workflow-node-inspector-surface.test.ts test/workflow-preflight-panel.test.ts test/workflow-template-canvas-surface.test.ts`

Expected: all focused tests PASS.

**Step 3: Run full verification**

Run: `cd frontend && npm run test`

Expected: all frontend tests PASS.

Run: `cd frontend && npm run build`

Expected: type checking and the Vite production build PASS.

**Step 4: Commit**

```bash
git add frontend/test/workflow-node-inspector-surface.test.ts \
  frontend/src/components/workflow/WorkflowNodeRunPanel.vue \
  frontend/src/components/workflow/WorkflowNodeStatusBadge.vue
git commit -m "fix(frontend): theme workflow inspector surfaces"
```
