# Task Center Type Tabs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a secondary type tab to Task Center so agent sessions and standalone tool tasks can be viewed separately.

**Architecture:** Keep backend APIs unchanged. Add a small frontend helper for type tab visibility and wire it into `frontend/src/views/tasks/List.vue`.

**Tech Stack:** Vue 3, TypeScript, Ant Design Vue, Pinia, Node test runner.

---

### Task 1: Add Failing Tests

**Files:**
- Modify: `frontend/test/task-agent-grouping.test.ts`

**Steps:**
1. Import new helpers that do not exist yet.
2. Add tests for `shouldShowAgentSection` and `shouldShowStandaloneSection`.
3. Add source integration assertions for `taskTypeTab`, `a-segmented`, and section wrappers.
4. Run `npx tsx --test test/task-agent-grouping.test.ts` and confirm it fails due missing exports/source markers.

### Task 2: Implement Helpers

**Files:**
- Modify: `frontend/src/views/tasks/agent-task-grouping.ts`

**Steps:**
1. Add `TaskContentTypeTab = 'all' | 'agent' | 'standalone'`.
2. Add `shouldShowAgentSection(tab)` and `shouldShowStandaloneSection(tab)`.
3. Run focused test and confirm helper assertions pass while source integration still fails if page is not wired.

### Task 3: Wire Task Center UI

**Files:**
- Modify: `frontend/src/views/tasks/List.vue`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`

**Steps:**
1. Add `taskTypeTab` state and segmented options.
2. Render the segmented control below existing filters.
3. Split list rendering into agent and standalone sections.
4. Reset pagination when type tab changes.
5. Add localized labels.

### Task 4: Verify

**Commands:**
- `npx tsx --test test/task-agent-grouping.test.ts test/workflow-inline-results.test.ts test/task-result-visualization.test.ts`
- `npm run build`

**Expected:**
- Tests pass.
- Build exits with code 0. Existing Vite warnings may remain.
