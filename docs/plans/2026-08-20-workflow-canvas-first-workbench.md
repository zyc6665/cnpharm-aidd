# Workflow Canvas-first Workbench Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the workflow page into a canvas-first drug discovery workbench with large node panels, inline result preview, and resizable tool/result sidebars.

**Architecture:** Keep the existing Vue workflow stores and canvas engine. Add a workbench shell around the current board, replace the small node view with a panel node view, extract standalone node execution into a reusable composable, and move running task polling to the workbench layer.

**Tech Stack:** Vue 3 Composition API, TypeScript, Pinia, Ant Design Vue, Vitest, Vue Test Utils, existing workflow canvas/domain/task/artifact modules.

---

## Constraints

- Do not modify unrelated dirty files already present in the worktree.
- Use TDD for each implementation task: write or update the focused failing test first.
- Keep changes incremental and commit after each task.
- Avoid introducing a new canvas library in this iteration.
- Avoid rendering heavy 3D visualizers for every node at once; render them only for selected or expanded nodes.

## Task 1: Workbench Layout State

**Files:**
- Create: `frontend/src/composables/useWorkflowWorkbenchLayout.ts`
- Create: `frontend/src/composables/useWorkflowWorkbenchLayout.spec.ts`

**Step 1: Write the failing test**

Create `frontend/src/composables/useWorkflowWorkbenchLayout.spec.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { useWorkflowWorkbenchLayout } from './useWorkflowWorkbenchLayout'

describe('useWorkflowWorkbenchLayout', () => {
  it('clamps sidebar widths and toggles collapsed state', () => {
    const layout = useWorkflowWorkbenchLayout({
      left: { defaultWidth: 320, minWidth: 280, maxWidth: 480 },
      right: { defaultWidth: 380, minWidth: 320, maxWidth: 560 },
    })

    layout.setLeftWidth(900)
    layout.setRightWidth(120)

    expect(layout.leftWidth.value).toBe(480)
    expect(layout.rightWidth.value).toBe(320)

    layout.toggleLeftCollapsed()
    layout.toggleRightCollapsed()

    expect(layout.leftCollapsed.value).toBe(true)
    expect(layout.rightCollapsed.value).toBe(true)
  })
})
```

**Step 2: Run test to verify it fails**

Run: `npm test -- src/composables/useWorkflowWorkbenchLayout.spec.ts`

Expected: FAIL because `useWorkflowWorkbenchLayout` does not exist.

**Step 3: Write minimal implementation**

Create `frontend/src/composables/useWorkflowWorkbenchLayout.ts`:

```ts
import { ref } from 'vue'

interface SidebarConfig {
  defaultWidth: number
  minWidth: number
  maxWidth: number
}

interface WorkbenchLayoutOptions {
  left: SidebarConfig
  right: SidebarConfig
}

function clampWidth(value: number, config: SidebarConfig) {
  return Math.min(config.maxWidth, Math.max(config.minWidth, Math.round(value)))
}

export function useWorkflowWorkbenchLayout(options: WorkbenchLayoutOptions) {
  const leftWidth = ref(options.left.defaultWidth)
  const rightWidth = ref(options.right.defaultWidth)
  const leftCollapsed = ref(false)
  const rightCollapsed = ref(false)

  function setLeftWidth(value: number) {
    leftWidth.value = clampWidth(value, options.left)
  }

  function setRightWidth(value: number) {
    rightWidth.value = clampWidth(value, options.right)
  }

  function toggleLeftCollapsed() {
    leftCollapsed.value = !leftCollapsed.value
  }

  function toggleRightCollapsed() {
    rightCollapsed.value = !rightCollapsed.value
  }

  return {
    leftWidth,
    rightWidth,
    leftCollapsed,
    rightCollapsed,
    setLeftWidth,
    setRightWidth,
    toggleLeftCollapsed,
    toggleRightCollapsed,
  }
}
```

**Step 4: Run test to verify it passes**

Run: `npm test -- src/composables/useWorkflowWorkbenchLayout.spec.ts`

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/composables/useWorkflowWorkbenchLayout.ts frontend/src/composables/useWorkflowWorkbenchLayout.spec.ts
git commit -m "feat: add workflow workbench layout state"
```

## Task 2: Resizable Sidebar Component

**Files:**
- Create: `frontend/src/components/workflow/ResizableWorkbenchSidebar.vue`
- Create: `frontend/src/components/workflow/ResizableWorkbenchSidebar.spec.ts`

**Step 1: Write the failing test**

Create `frontend/src/components/workflow/ResizableWorkbenchSidebar.spec.ts`:

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ResizableWorkbenchSidebar from './ResizableWorkbenchSidebar.vue'

describe('ResizableWorkbenchSidebar', () => {
  it('renders slot content and emits width changes from the resize handle', async () => {
    const wrapper = mount(ResizableWorkbenchSidebar, {
      props: {
        side: 'left',
        width: 320,
        collapsed: false,
        minWidth: 280,
        maxWidth: 480,
      },
      slots: { default: '<div data-testid="sidebar-content">Tools</div>' },
    })

    expect(wrapper.find('[data-testid="sidebar-content"]').text()).toBe('Tools')
    expect(wrapper.attributes('style')).toContain('width: 320px')

    await wrapper.find('[data-testid="sidebar-resize-handle"]').trigger('pointerdown', { clientX: 320 })
    window.dispatchEvent(new PointerEvent('pointermove', { clientX: 380 }))
    window.dispatchEvent(new PointerEvent('pointerup'))

    expect(wrapper.emitted('update:width')?.at(-1)).toEqual([380])
  })

  it('uses collapsed width and emits collapsed toggle', async () => {
    const wrapper = mount(ResizableWorkbenchSidebar, {
      props: {
        side: 'right',
        width: 380,
        collapsed: true,
        minWidth: 320,
        maxWidth: 560,
      },
    })

    expect(wrapper.attributes('style')).toContain('width: 56px')
    await wrapper.find('[data-testid="sidebar-collapse-toggle"]').trigger('click')
    expect(wrapper.emitted('update:collapsed')).toEqual([[false]])
  })
})
```

**Step 2: Run test to verify it fails**

Run: `npm test -- src/components/workflow/ResizableWorkbenchSidebar.spec.ts`

Expected: FAIL because the component does not exist.

**Step 3: Write minimal implementation**

Create `ResizableWorkbenchSidebar.vue` with props `side`, `width`, `collapsed`, `minWidth`, `maxWidth`; emit `update:width` and `update:collapsed`; implement pointer-based resizing with no dependency.

Important implementation details:

```ts
const COLLAPSED_WIDTH = 56

const sidebarStyle = computed(() => ({
  width: `${props.collapsed ? COLLAPSED_WIDTH : props.width}px`,
}))

function clamp(value: number) {
  return Math.min(props.maxWidth, Math.max(props.minWidth, Math.round(value)))
}

function handlePointerDown(event: PointerEvent) {
  const startX = event.clientX
  const startWidth = props.width
  const direction = props.side === 'left' ? 1 : -1

  const handleMove = (moveEvent: PointerEvent) => {
    emit('update:width', clamp(startWidth + (moveEvent.clientX - startX) * direction))
  }

  const handleUp = () => {
    window.removeEventListener('pointermove', handleMove)
    window.removeEventListener('pointerup', handleUp)
  }

  window.addEventListener('pointermove', handleMove)
  window.addEventListener('pointerup', handleUp, { once: true })
}
```

**Step 4: Run test to verify it passes**

Run: `npm test -- src/components/workflow/ResizableWorkbenchSidebar.spec.ts`

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/components/workflow/ResizableWorkbenchSidebar.vue frontend/src/components/workflow/ResizableWorkbenchSidebar.spec.ts
git commit -m "feat: add resizable workflow sidebars"
```

## Task 3: Workbench Header and Shell

**Files:**
- Create: `frontend/src/components/workflow/WorkflowWorkbenchHeader.vue`
- Create: `frontend/src/components/workflow/WorkflowWorkbenchShell.vue`
- Create: `frontend/src/components/workflow/WorkflowWorkbenchShell.spec.ts`
- Modify: `frontend/src/views/workflow/index.vue`

**Step 1: Write the failing test**

Create `frontend/src/components/workflow/WorkflowWorkbenchShell.spec.ts`:

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkflowWorkbenchShell from './WorkflowWorkbenchShell.vue'

describe('WorkflowWorkbenchShell', () => {
  it('renders full workbench regions and keeps canvas as the primary area', () => {
    const wrapper = mount(WorkflowWorkbenchShell, {
      props: {
        workflowName: 'Docking Flow',
        readyCount: 1,
        runningCount: 0,
        completedCount: 0,
        failedCount: 0,
        leftWidth: 320,
        rightWidth: 380,
        leftCollapsed: false,
        rightCollapsed: false,
      },
      slots: {
        left: '<div data-testid="tool-library">tools</div>',
        canvas: '<div data-testid="canvas-region">canvas</div>',
        right: '<div data-testid="results-center">results</div>',
      },
      global: {
        stubs: {
          AButton: { template: '<button><slot /></button>' },
          ATag: { template: '<span><slot /></span>' },
          ASpace: { template: '<div><slot /></div>' },
        },
      },
    })

    expect(wrapper.find('[data-testid="workflow-workbench"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="tool-library"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="canvas-region"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="results-center"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Docking Flow')
  })
})
```

**Step 2: Run test to verify it fails**

Run: `npm test -- src/components/workflow/WorkflowWorkbenchShell.spec.ts`

Expected: FAIL because shell/header do not exist.

**Step 3: Write minimal implementation**

Implement `WorkflowWorkbenchHeader.vue` as a compact command bar with workflow name, status counts, and action slots.

Implement `WorkflowWorkbenchShell.vue` using `ResizableWorkbenchSidebar` and slots:

```vue
<template>
  <section class="workflow-workbench" data-testid="workflow-workbench">
    <WorkflowWorkbenchHeader
      :workflow-name="workflowName"
      :ready-count="readyCount"
      :running-count="runningCount"
      :completed-count="completedCount"
      :failed-count="failedCount"
    >
      <template #actions><slot name="actions" /></template>
    </WorkflowWorkbenchHeader>

    <div class="workflow-workbench__body">
      <ResizableWorkbenchSidebar side="left" ...>
        <slot name="left" />
      </ResizableWorkbenchSidebar>
      <main class="workflow-workbench__canvas"><slot name="canvas" /></main>
      <ResizableWorkbenchSidebar side="right" ...>
        <slot name="right" />
      </ResizableWorkbenchSidebar>
    </div>
  </section>
</template>
```

Do not yet remove old workflow page blocks in this task.

**Step 4: Run test to verify it passes**

Run: `npm test -- src/components/workflow/WorkflowWorkbenchShell.spec.ts src/components/workflow/ResizableWorkbenchSidebar.spec.ts`

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/components/workflow/WorkflowWorkbenchHeader.vue frontend/src/components/workflow/WorkflowWorkbenchShell.vue frontend/src/components/workflow/WorkflowWorkbenchShell.spec.ts frontend/src/views/workflow/index.vue
git commit -m "feat: add workflow workbench shell"
```

## Task 4: Mount Workbench Shell in Workflow Page

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Test: existing relevant workflow component tests through build coverage

**Step 1: Write the failing test**

If no page-level spec exists for `frontend/src/views/workflow/index.vue`, add a focused test only if the current test harness already supports the page dependencies. Otherwise use `WorkflowWorkbenchShell.spec.ts` as component coverage and rely on build for integration.

Preferred page assertion if practical:

```ts
expect(wrapper.find('[data-testid="workflow-workbench"]').exists()).toBe(true)
expect(wrapper.find('.workflow-canvas-layout').exists()).toBe(false)
```

**Step 2: Run test to verify it fails**

Run the new or updated spec if added. If no page spec is practical, skip to Step 3 and validate through `npm run build` after integration.

**Step 3: Integrate the shell**

Replace the manual tab body structure in `frontend/src/views/workflow/index.vue`:

- Keep `ProjectWorkspaceNav` if `routeProjectId` exists.
- Remove the large centered `AppPageHeader` from the workflow workbench viewport.
- Move workflow name/save/load/run controls into the shell `actions` slot or `WorkflowWorkbenchHeader` props.
- Move `WorkflowControlNodePalette` and `WorkflowToolPalette` into the left slot.
- Move `WorkflowNodeInspector`, `WorkflowTaskResultPanel`, `WorkflowResultsReportPanel`, `WorkflowArtifactPanel`, `WorkflowRunHistoryPanel`, and run status/preflight summaries into the right slot using compact tabs.
- Put `WorkflowCanvasBoard` in the canvas slot.

Keep existing handler names and store state: `handleAddToolNode`, `handleAddControlNode`, `workflowStore.moveNode`, `handleAddEdge`, `handleDeleteEdge`, `handleRunWorkflowDefinition`.

**Step 4: Update page styles**

Replace old `.workflow-deck`, `.workflow-canvas-layout`, `.workflow-step-rail`, `.workflow-results-region` rules with workbench rules:

```less
.workflow-page {
  min-height: calc(100vh - @header-height);
  padding: 0;
  background: @bg-light;
}

.workflow-shell {
  width: 100%;
  max-width: none;
}

.workflow-workbench :deep(.workflow-canvas-board) {
  height: 100%;
  border-radius: 0;
}
```

**Step 5: Run verification**

Run: `npm test -- src/components/workflow/WorkflowWorkbenchShell.spec.ts src/components/workflow/WorkflowToolPalette.spec.ts src/components/workflow/WorkflowCanvasBoard.spec.ts`

Run: `npm run build`

Expected: tests and build pass.

**Step 6: Commit**

```bash
git add frontend/src/views/workflow/index.vue frontend/src/components/workflow/WorkflowWorkbenchShell.vue frontend/src/components/workflow/WorkflowWorkbenchHeader.vue
git commit -m "feat: mount canvas-first workflow workbench"
```

## Task 5: Panel Node View

**Files:**
- Create: `frontend/src/components/workflow/WorkflowCanvasPanelNode.vue`
- Create: `frontend/src/components/workflow/WorkflowCanvasPanelNode.spec.ts`
- Modify: `frontend/src/components/workflow/WorkflowCanvasBoard.vue`
- Modify: `frontend/src/components/workflow/WorkflowCanvasBoard.spec.ts`

**Step 1: Write the failing test**

Create `WorkflowCanvasPanelNode.spec.ts`:

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkflowCanvasPanelNode from './WorkflowCanvasPanelNode.vue'

describe('WorkflowCanvasPanelNode', () => {
  it('renders a large node panel with status, run action, and preview slot', async () => {
    const wrapper = mount(WorkflowCanvasPanelNode, {
      props: {
        node: {
          id: 'fetch-pdb-node',
          type: 'tool',
          titleKey: 'Fetch PDB',
          position: { x: 40, y: 80 },
          producedOutputTypes: ['protein_structure@1'],
        },
        title: 'Fetch PDB',
        status: 'ready',
        selected: true,
        scale: 1,
      },
      slots: { preview: '<div data-testid="node-preview">PDB preview</div>' },
      global: {
        stubs: {
          AButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' },
          ATag: { template: '<span><slot /></span>' },
          WorkflowNodeStatusBadge: { template: '<span data-testid="node-status" />' },
        },
      },
    })

    expect(wrapper.classes()).toContain('workflow-canvas-panel-node')
    expect(wrapper.text()).toContain('Fetch PDB')
    expect(wrapper.find('[data-testid="node-preview"]').exists()).toBe(true)

    await wrapper.find('[data-testid="run-node-button"]').trigger('click')
    expect(wrapper.emitted('run-node')).toEqual([['fetch-pdb-node']])
  })
})
```

**Step 2: Run test to verify it fails**

Run: `npm test -- src/components/workflow/WorkflowCanvasPanelNode.spec.ts`

Expected: FAIL because component does not exist.

**Step 3: Implement panel node**

Base it on `WorkflowCanvasNode.vue` drag/connect behavior, but increase panel dimensions and add named slots:

- `summary`
- `preview`
- `outputs`
- `actions`

Emit existing events plus `run-node` and `toggle-expanded`.

Keep port data attributes compatible with existing tests:

```vue
<button :data-node-port="`${node.id}-input`" />
<button :data-node-port="`${node.id}-output`" />
```

**Step 4: Modify `WorkflowCanvasBoard.vue`**

- Replace `WorkflowCanvasNodeView` import with `WorkflowCanvasPanelNode`.
- Change constants to first-version fixed panel size:

```ts
const NODE_WIDTH = 380
const NODE_HEIGHT = 280
const CANVAS_PADDING = 96
```

- Pass task/preview slots later; for this task render default summary only.
- Keep edge source and target math based on the new constants.

**Step 5: Update board tests**

Update `WorkflowCanvasBoard.spec.ts` expectations only where dimensions affect drop/edge behavior. Port selectors should remain unchanged.

**Step 6: Run verification**

Run: `npm test -- src/components/workflow/WorkflowCanvasPanelNode.spec.ts src/components/workflow/WorkflowCanvasBoard.spec.ts`

Expected: PASS.

**Step 7: Commit**

```bash
git add frontend/src/components/workflow/WorkflowCanvasPanelNode.vue frontend/src/components/workflow/WorkflowCanvasPanelNode.spec.ts frontend/src/components/workflow/WorkflowCanvasBoard.vue frontend/src/components/workflow/WorkflowCanvasBoard.spec.ts
git commit -m "feat: render workflow nodes as canvas panels"
```

## Task 6: Extract Standalone Node Runner

**Files:**
- Create: `frontend/src/composables/useStandaloneNodeRun.ts`
- Create: `frontend/src/composables/useStandaloneNodeRun.spec.ts`
- Modify: `frontend/src/components/workflow/WorkflowNodeRunPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowNodeRunPanel.spec.ts`

**Step 1: Write the failing composable test**

Create `useStandaloneNodeRun.spec.ts` with mocked `createTask`, `getTaskDetail`, `uploadFile`, and stores. Cover:

- Creates `/tasks` payload for selected tool.
- Records task on `workflowStore.recordNodeTask`.
- Polls until terminal status.
- Refreshes artifacts on success.

Test skeleton:

```ts
it('creates a standalone task, binds it to the node, and refreshes terminal status', async () => {
  const runner = useStandaloneNodeRun({ nodeId: 'fetch-pdb-node', projectId: null })
  await runner.run({
    tool: mockTool,
    selectedToolSlug: 'builtin-fetch-pdb',
    flattenedSchema: { type: 'object', properties: { pdb_id: { type: 'string' } }, required: ['pdb_id'] },
    formState: { pdb_id: '1CRN' },
    fileList: {},
    selectedArtifacts: {},
    executorType: 'builtin',
    contractArtifactInputs: [],
  })

  expect(createTask).toHaveBeenCalledWith(expect.objectContaining({ tool_id: mockTool.id }))
  expect(workflowStore.taskByNode['fetch-pdb-node']).toMatchObject({ id: 'task-1' })
})
```

**Step 2: Run test to verify it fails**

Run: `npm test -- src/composables/useStandaloneNodeRun.spec.ts`

Expected: FAIL because composable does not exist.

**Step 3: Move logic from `WorkflowNodeRunPanel.vue` into composable**

Move these functions without changing behavior:

- `resolveUploadedFiles`
- `withBuiltinInputs`
- `runCurrentNode`
- `startStandaloneTaskPolling`
- `stopStandaloneTaskPolling`
- `refreshTaskBindings`

Composable API:

```ts
export function useStandaloneNodeRun(input: {
  nodeId: Ref<string> | string
  projectId?: Ref<string | null | undefined> | string | null
}) {
  return {
    submitting,
    run,
    startPolling,
    stopPolling,
  }
}
```

**Step 4: Refactor `WorkflowNodeRunPanel.vue`**

- Keep form rendering and tool detail loading in the component.
- Use `useStandaloneNodeRun` for submit and polling.
- Keep public behavior and existing tests unchanged.

**Step 5: Run verification**

Run: `npm test -- src/composables/useStandaloneNodeRun.spec.ts src/components/workflow/WorkflowNodeRunPanel.spec.ts`

Expected: PASS.

**Step 6: Commit**

```bash
git add frontend/src/composables/useStandaloneNodeRun.ts frontend/src/composables/useStandaloneNodeRun.spec.ts frontend/src/components/workflow/WorkflowNodeRunPanel.vue frontend/src/components/workflow/WorkflowNodeRunPanel.spec.ts
git commit -m "refactor: extract standalone workflow node runner"
```

## Task 7: Inline Node Preview

**Files:**
- Create: `frontend/src/components/workflow/WorkflowNodeInlinePreview.vue`
- Create: `frontend/src/components/workflow/WorkflowNodeInlinePreview.spec.ts`
- Modify: `frontend/src/components/workflow/WorkflowCanvasBoard.vue`

**Step 1: Write the failing test**

Create `WorkflowNodeInlinePreview.spec.ts`:

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkflowNodeInlinePreview from './WorkflowNodeInlinePreview.vue'

describe('WorkflowNodeInlinePreview', () => {
  it('shows a lightweight running state while task is running', () => {
    const wrapper = mount(WorkflowNodeInlinePreview, {
      props: {
        selected: true,
        task: { id: 'task-1', status: 'running', progress: 40, output_files: [] },
        artifacts: [],
      },
      global: { stubs: { AProgress: true, AEmpty: true, ResultVisualizationPanel: true } },
    })

    expect(wrapper.text()).toContain('40%')
  })

  it('lazy-renders visualization only for selected successful nodes', () => {
    const wrapper = mount(WorkflowNodeInlinePreview, {
      props: {
        selected: false,
        task: { id: 'task-1', status: 'success', progress: 100, output_files: [{ id: 'f1', filename: 'ligand.sdf', url: '/f1' }] },
        artifacts: [],
      },
      global: { stubs: { ResultVisualizationPanel: { template: '<div data-testid="visualization" />' }, AEmpty: true } },
    })

    expect(wrapper.find('[data-testid="visualization"]').exists()).toBe(false)
  })
})
```

**Step 2: Run test to verify it fails**

Run: `npm test -- src/components/workflow/WorkflowNodeInlinePreview.spec.ts`

Expected: FAIL because component does not exist.

**Step 3: Implement preview component**

Behavior:

- No task: show compact empty state.
- Pending/running: show progress and progress message.
- Failure/canceled: show compact error.
- Success + selected/expanded: render `ResultVisualizationPanel` if output files or typed artifacts exist.
- Success + not selected: render output count/file chips only.

Use `normalizeTaskStatus` from `@/domain/tasks` if available.

**Step 4: Wire preview into board**

Add props to `WorkflowCanvasBoard.vue`:

```ts
taskByNode?: Record<string, WorkflowTaskRef>
artifacts?: ArtifactFile[]
```

Pass matching task into `WorkflowCanvasPanelNode` preview slot:

```vue
<template #preview>
  <WorkflowNodeInlinePreview
    :selected="node.id === activeNodeId"
    :task="taskByNode?.[node.id] ?? null"
    :artifacts="artifacts ?? []"
  />
</template>
```

**Step 5: Run verification**

Run: `npm test -- src/components/workflow/WorkflowNodeInlinePreview.spec.ts src/components/workflow/WorkflowCanvasBoard.spec.ts`

Expected: PASS.

**Step 6: Commit**

```bash
git add frontend/src/components/workflow/WorkflowNodeInlinePreview.vue frontend/src/components/workflow/WorkflowNodeInlinePreview.spec.ts frontend/src/components/workflow/WorkflowCanvasBoard.vue
git commit -m "feat: preview workflow node results inline"
```

## Task 8: Workbench-Level Node Task Polling

**Files:**
- Create: `frontend/src/composables/useWorkflowNodeTaskPolling.ts`
- Create: `frontend/src/composables/useWorkflowNodeTaskPolling.spec.ts`
- Modify: `frontend/src/components/workflow/WorkflowWorkbenchShell.vue` or `frontend/src/views/workflow/index.vue`

**Step 1: Write the failing test**

Create `useWorkflowNodeTaskPolling.spec.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useWorkflowNodeTaskPolling } from './useWorkflowNodeTaskPolling'

describe('useWorkflowNodeTaskPolling', () => {
  it('polls all non-terminal node tasks and stops terminal tasks', async () => {
    vi.useFakeTimers()
    const taskByNode = ref({
      a: { id: 'task-a', status: 'running', progress: 10 },
      b: { id: 'task-b', status: 'success', progress: 100 },
    })
    const recordNodeTask = vi.fn()

    useWorkflowNodeTaskPolling({ taskByNode, recordNodeTask, intervalMs: 1000 })
    await vi.advanceTimersByTimeAsync(1000)

    expect(recordNodeTask).toHaveBeenCalledWith('a', expect.objectContaining({ id: 'task-a' }))
    expect(recordNodeTask).not.toHaveBeenCalledWith('b', expect.anything())
    vi.useRealTimers()
  })
})
```

Mock `getTaskDetail` to return terminal or running data.

**Step 2: Run test to verify it fails**

Run: `npm test -- src/composables/useWorkflowNodeTaskPolling.spec.ts`

Expected: FAIL because composable does not exist.

**Step 3: Implement polling composable**

Behavior:

- Watch all `taskByNode` entries.
- Start polling only task statuses that are not terminal.
- Call `getTaskDetail(taskId)`.
- Update `workflowStore.recordNodeTask(nodeId, task)`.
- Refresh artifacts after a task transitions to success.
- Clear timers on unmount/stop.

**Step 4: Integrate polling**

Call the composable once at workbench/page level, not inside each node panel:

```ts
useWorkflowNodeTaskPolling({
  taskByNode: computed(() => workflowStore.taskByNode),
  recordNodeTask: workflowStore.recordNodeTask,
  refreshArtifacts: () => artifactsStore.fetchArtifacts({ page: 1, page_size: 100 }),
})
```

Remove duplicated polling from `WorkflowNodeRunPanel.vue` only after the extracted runner and global polling overlap safely. The node runner may keep polling for immediate feedback, but the page-level poller must be the source that restores persisted running tasks.

**Step 5: Run verification**

Run: `npm test -- src/composables/useWorkflowNodeTaskPolling.spec.ts src/components/workflow/WorkflowNodeRunPanel.spec.ts`

Expected: PASS.

**Step 6: Commit**

```bash
git add frontend/src/composables/useWorkflowNodeTaskPolling.ts frontend/src/composables/useWorkflowNodeTaskPolling.spec.ts frontend/src/views/workflow/index.vue frontend/src/components/workflow/WorkflowWorkbenchShell.vue frontend/src/components/workflow/WorkflowNodeRunPanel.vue
git commit -m "feat: poll workflow node tasks at workbench level"
```

## Task 9: Right Sidebar Result Center Tabs

**Files:**
- Create: `frontend/src/components/workflow/WorkflowResultsSidebar.vue`
- Create: `frontend/src/components/workflow/WorkflowResultsSidebar.spec.ts`
- Modify: `frontend/src/views/workflow/index.vue`

**Step 1: Write the failing test**

Create `WorkflowResultsSidebar.spec.ts`:

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkflowResultsSidebar from './WorkflowResultsSidebar.vue'

describe('WorkflowResultsSidebar', () => {
  it('shows selected node result, workflow report, artifacts, and run history tabs', () => {
    const wrapper = mount(WorkflowResultsSidebar, {
      props: {
        activeNode: null,
        workflowName: 'Docking Flow',
        reportRows: [],
        artifacts: [],
        runs: [],
      },
      global: {
        stubs: {
          ATabs: { template: '<div><slot /></div>' },
          ATabPane: { template: '<section><slot /></section>' },
          WorkflowTaskResultPanel: true,
          WorkflowResultsReportPanel: true,
          WorkflowArtifactPanel: true,
          WorkflowRunHistoryPanel: true,
        },
      },
    })

    expect(wrapper.text()).toContain('节点结果')
    expect(wrapper.text()).toContain('结果报告')
    expect(wrapper.text()).toContain('产物')
    expect(wrapper.text()).toContain('历史')
  })
})
```

**Step 2: Run test to verify it fails**

Run: `npm test -- src/components/workflow/WorkflowResultsSidebar.spec.ts`

Expected: FAIL because component does not exist.

**Step 3: Implement sidebar component**

Use Ant Design tabs and wrap existing components. Keep props narrow and pass through existing event handlers:

- `sync`
- `cancel`
- `retry-node`
- `refresh-runs`
- `load-more-runs`
- `view-task-detail`
- `select-node`

**Step 4: Integrate into right slot**

Replace direct right-side composition in `index.vue` with `WorkflowResultsSidebar`.

**Step 5: Run verification**

Run: `npm test -- src/components/workflow/WorkflowResultsSidebar.spec.ts src/components/workflow/WorkflowWorkbenchShell.spec.ts`

Expected: PASS.

**Step 6: Commit**

```bash
git add frontend/src/components/workflow/WorkflowResultsSidebar.vue frontend/src/components/workflow/WorkflowResultsSidebar.spec.ts frontend/src/views/workflow/index.vue
git commit -m "feat: add workflow result center sidebar"
```

## Task 10: Visual Polish and Responsive Behavior

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowWorkbenchShell.vue`
- Modify: `frontend/src/components/workflow/WorkflowCanvasPanelNode.vue`
- Modify: `frontend/src/components/workflow/WorkflowCanvasBoard.vue`
- Modify: `frontend/src/views/workflow/index.vue`

**Step 1: Add or update focused tests**

Add assertions to existing specs for:

- Collapsed sidebars do not hide canvas.
- Canvas board fills available workbench height.
- Node panel text truncates instead of overflowing.

**Step 2: Run tests to verify current gaps**

Run: `npm test -- src/components/workflow/WorkflowWorkbenchShell.spec.ts src/components/workflow/WorkflowCanvasPanelNode.spec.ts src/components/workflow/WorkflowCanvasBoard.spec.ts`

Expected: FAIL if the new assertions are not yet satisfied.

**Step 3: Apply styles**

Style targets:

- `.workflow-workbench { height: calc(100vh - @header-height); min-height: 720px; overflow: hidden; }`
- `.workflow-workbench__body { min-height: 0; display: flex; }`
- `.workflow-workbench__canvas { flex: 1; min-width: 0; min-height: 0; }`
- `.workflow-canvas-board { height: 100%; }`
- `.canvas-viewport { flex: 1; min-height: 0; }`
- `.workflow-canvas-panel-node` uses stable width/height and internal scroll/line clamp.

**Step 4: Run verification**

Run: `npm test -- src/components/workflow/WorkflowWorkbenchShell.spec.ts src/components/workflow/WorkflowCanvasPanelNode.spec.ts src/components/workflow/WorkflowCanvasBoard.spec.ts`

Run: `npm run build`

Expected: PASS. Build may keep existing chunk/eval warnings but must not fail.

**Step 5: Commit**

```bash
git add frontend/src/components/workflow/WorkflowWorkbenchShell.vue frontend/src/components/workflow/WorkflowCanvasPanelNode.vue frontend/src/components/workflow/WorkflowCanvasBoard.vue frontend/src/views/workflow/index.vue
git commit -m "style: polish canvas-first workflow workbench"
```

## Final Verification

Run the focused suite:

```bash
npm test -- src/composables/useWorkflowWorkbenchLayout.spec.ts src/components/workflow/ResizableWorkbenchSidebar.spec.ts src/components/workflow/WorkflowWorkbenchShell.spec.ts src/components/workflow/WorkflowCanvasPanelNode.spec.ts src/components/workflow/WorkflowNodeInlinePreview.spec.ts src/composables/useStandaloneNodeRun.spec.ts src/composables/useWorkflowNodeTaskPolling.spec.ts src/components/workflow/WorkflowResultsSidebar.spec.ts src/components/workflow/WorkflowCanvasBoard.spec.ts src/components/workflow/WorkflowNodeRunPanel.spec.ts src/components/workflow/WorkflowToolPalette.spec.ts
```

Run production build:

```bash
npm run build
```

Check git scope:

```bash
git status --short
git diff --check
```

Expected final state:

- Only intended workflow frontend files and tests changed.
- Existing unrelated dirty files remain untouched.
- Tests pass.
- Build passes.
- No whitespace errors.
