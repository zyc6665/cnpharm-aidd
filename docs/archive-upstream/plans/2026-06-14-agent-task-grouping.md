# Agent Task Grouping Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Task Center show each AIDD agent run as one collapsed card, with its tool-step tasks shown only after expansion.

**Architecture:** Keep backend APIs unchanged for the first pass. Add frontend grouping helpers that merge `Task[]` with `AiddAgentRun[]`, hide visible task cards linked from agent steps, and render agent run cards alongside ordinary task cards.

**Tech Stack:** Vue 3, Pinia, Ant Design Vue, TypeScript, Node test runner with `tsx`.

---

### Task 1: Add Grouping Helper Tests

**Files:**
- Create: `frontend/test/task-agent-grouping.test.ts`
- Create: `frontend/src/views/tasks/agent-task-grouping.ts`

**Step 1: Write failing tests**

Cover:

- Agent step `task_id`s are collected.
- Ordinary display tasks exclude tasks linked by agent steps.
- Agent runs are filtered by tab status: non-terminal for `running`, terminal for `history`.
- Keyword search matches agent message and step tool slug.

**Step 2: Run the focused test**

Run: `cd frontend && npx tsx --test test/task-agent-grouping.test.ts`

Expected: FAIL because `agent-task-grouping.ts` does not exist.

### Task 2: Implement Grouping Helpers

**Files:**
- Create: `frontend/src/views/tasks/agent-task-grouping.ts`

**Step 1: Implement types and helpers**

Add:

- `isTerminalAgentRunStatus(status)`
- `isActiveAgentRunStatus(status)`
- `collectAgentTaskIds(runs)`
- `filterStandaloneTasks(tasks, agentTaskIds)`
- `filterAgentRunsForTaskCenter(runs, options)`
- `getAgentRunProgress(run)`

**Step 2: Run focused tests**

Run: `cd frontend && npx tsx --test test/task-agent-grouping.test.ts`

Expected: PASS.

### Task 3: Add Agent Card Component

**Files:**
- Create: `frontend/src/views/tasks/AgentRunTaskCard.vue`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`

**Step 1: Implement card**

Create a compact operational card:

- Header with message/summary, status tag, run id.
- Meta row with created time, finished time, step progress.
- Default collapsed.
- Expanded step list with step index, tool slug, status, error message, and view task action.

**Step 2: Add locale keys**

Add labels under `tasks`, such as:

- `agentRun`
- `agentRunSteps`
- `agentRunProgress`
- `agentViewTask`
- `agentNoLinkedTask`

### Task 4: Integrate Into Task Center

**Files:**
- Modify: `frontend/src/views/tasks/List.vue`
- Modify: `frontend/src/stores/agents.ts` only if needed for loading state access

**Step 1: Load agent runs**

Import `useAgentsStore`. In `onMounted`, fetch tasks, tools, and agent runs together.

**Step 2: Build mixed display list**

Use grouping helpers to compute:

- `agentTaskIds`
- `standaloneTasks`
- `displayAgentRuns`
- `hasDisplayItems`

**Step 3: Render agent cards**

Render `AgentRunTaskCard` before/among ordinary tasks. Preserve ordinary task card behavior.

**Step 4: Keep existing actions**

Do not add agent delete/cancel in this pass unless already available elsewhere. The card should only expand and link step tasks.

### Task 5: Verify

**Files:**
- Test: `frontend/test/task-agent-grouping.test.ts`
- Existing adjacent tests: `frontend/test/workflow-inline-results.test.ts`

**Step 1: Run focused tests**

Run: `cd frontend && npx tsx --test test/task-agent-grouping.test.ts`

Expected: PASS.

**Step 2: Run adjacent frontend tests**

Run: `cd frontend && npx tsx --test test/task-agent-grouping.test.ts test/workflow-inline-results.test.ts`

Expected: PASS.

**Step 3: Build**

Run: `cd frontend && npm run build`

Expected: PASS, with only existing Vite chunk warnings if present.
