# Template Workflow Canvas Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the first version of a template-based workflow node canvas for `/workflow`, using fixed templates now and preserving a clean upgrade path to a free drag-and-drop canvas later.

**Architecture:** Keep backend changes out of phase one. Implement a frontend template graph model (`nodes`, `edges`, `position`) and render it in the existing workflow page. Reuse current task creation, artifact fetching, tool selection, and workflow store capabilities.

**Tech Stack:** Vue 3, TypeScript, Pinia, Ant Design Vue, Less, existing `node:test` frontend test style, existing FastAPI task/tool/file APIs.

---

## Important Constraints

- Do not implement free dragging, custom connections, or backend workflow persistence in this phase.
- Do not remove the existing agent mode.
- Do not break existing manual workflow behavior until the node canvas replacement is verified.
- Follow the design in `docs/plans/2026-06-15-template-workflow-canvas-design.md`.
- Git commits in this plan are suggested checkpoints only. In this repository, only run `git commit` after explicit user approval.

## Task 1: Add Workflow Template Types

**Files:**
- Create: `frontend/src/workflow/template-types.ts`
- Test: `frontend/test/workflow-template-types.test.ts`

**Step 1: Write the failing test**

Create `frontend/test/workflow-template-types.test.ts`:

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const source = readFileSync(resolve('src/workflow/template-types.ts'), 'utf8')

test('workflow template model exposes graph primitives', () => {
  assert.equal(source.includes('WorkflowTemplate'), true)
  assert.equal(source.includes('WorkflowCanvasNode'), true)
  assert.equal(source.includes('WorkflowCanvasEdge'), true)
  assert.equal(source.includes('position'), true)
})
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd frontend
node --test test/workflow-template-types.test.ts
```

Expected: FAIL because `src/workflow/template-types.ts` does not exist.

**Step 3: Add template types**

Create `frontend/src/workflow/template-types.ts`:

```ts
import type { WorkflowArtifactSemanticType, WorkflowStepKey } from './artifact-types'

export type WorkflowTemplateKind = 'aidd' | 'docking' | 'pocket' | 'screening'
export type WorkflowCanvasNodeType = 'input' | 'tool' | 'artifact' | 'result'

export interface WorkflowTemplate {
  id: string
  kind: WorkflowTemplateKind
  nameKey: string
  descriptionKey?: string
  nodes: WorkflowCanvasNode[]
  edges: WorkflowCanvasEdge[]
}

export interface WorkflowCanvasNode {
  id: string
  type: WorkflowCanvasNodeType
  stepKey?: WorkflowStepKey
  toolSlugs?: string[]
  recommendedToolSlug?: string
  titleKey: string
  descriptionKey?: string
  position: { x: number; y: number }
  requiredInputTypes?: WorkflowArtifactSemanticType[]
  producedOutputTypes?: WorkflowArtifactSemanticType[]
}

export interface WorkflowCanvasEdge {
  id: string
  source: string
  target: string
  artifactType?: WorkflowArtifactSemanticType
  labelKey?: string
}
```

**Step 4: Run test**

Run:

```bash
cd frontend
node --test test/workflow-template-types.test.ts
```

Expected: PASS.

## Task 2: Add AIDD Template Definition

**Files:**
- Create: `frontend/src/workflow/templates.ts`
- Test: `frontend/test/workflow-templates.test.ts`

**Step 1: Write the failing test**

Create a test that imports `AIDD_WORKFLOW_TEMPLATE` and asserts:

- It has at least 7 nodes.
- It includes `input`, `tool`, and `result` node types.
- Every edge source and target points to an existing node.
- At least one node has `position`.

**Step 2: Run test**

Run:

```bash
cd frontend
node --test test/workflow-templates.test.ts
```

Expected: FAIL because the template file is missing.

**Step 3: Implement template**

Create `frontend/src/workflow/templates.ts` and define:

- `AIDD_WORKFLOW_TEMPLATE`
- `WORKFLOW_TEMPLATES`
- `getWorkflowTemplateById(templateId: string)`

Use node IDs such as:

- `input-protein`
- `tool-pocket-exploration`
- `tool-molecule-generation`
- `tool-docking`
- `tool-property-prediction`
- `tool-lead-optimization`
- `result-summary`

**Step 4: Run test**

Run:

```bash
cd frontend
node --test test/workflow-templates.test.ts
```

Expected: PASS.

## Task 3: Add Node State Helpers

**Files:**
- Create: `frontend/src/workflow/template-state.ts`
- Test: `frontend/test/workflow-template-state.test.ts`

**Step 1: Write failing tests**

Cover these cases:

- Missing selected tool for multi-tool node returns `needs_tool_selection`.
- Missing required input returns `idle`.
- Ready node returns `ready`.
- Running task returns `running`.
- Failed task returns `failed`.
- Successful task returns `completed`.

**Step 2: Run test**

Run:

```bash
cd frontend
node --test test/workflow-template-state.test.ts
```

Expected: FAIL.

**Step 3: Implement helpers**

Implement functions:

```ts
export function resolveWorkflowCanvasNodeStatus(input: {
  node: WorkflowCanvasNode
  selectedToolSlug?: string | null
  hasRequiredInputs: boolean
  task?: WorkflowTaskRef | null
}): WorkflowStepStatus
```

Map task statuses through existing `frontend/src/workflow/task-state.ts` where possible.

**Step 4: Run test**

Run:

```bash
cd frontend
node --test test/workflow-template-state.test.ts
```

Expected: PASS.

## Task 4: Extend Workflow Store For Template Sessions

**Files:**
- Modify: `frontend/src/stores/workflow.ts`
- Test: `frontend/test/workflow-template-session.test.ts`

**Step 1: Write failing test**

Assert the store source includes:

- `templateId`
- `activeNodeId`
- `selectedToolByNode`
- `nodeFormDrafts`
- `taskByNode`
- `artifactBindingsByNode`

**Step 2: Run test**

Run:

```bash
cd frontend
node --test test/workflow-template-session.test.ts
```

Expected: FAIL.

**Step 3: Extend store minimally**

Add state and actions:

- `setTemplate(templateId: string)`
- `setActiveNode(nodeId: string | null)`
- `selectNodeTool(nodeId: string, toolSlug: string)`
- `setNodeFormDraft(nodeId: string, draft: Record<string, unknown>)`
- `recordNodeTask(nodeId: string, task: WorkflowTaskRef)`
- `setNodeArtifactBinding(nodeId: string, field: string, artifactId: string)`

Persist these fields with existing Pinia persistence.

**Step 4: Run related tests**

Run:

```bash
cd frontend
node --test test/workflow-template-session.test.ts
node --test test/aidd-workflow-logic.test.ts
```

Expected: PASS.

## Task 5: Build Static Canvas Components

**Files:**
- Create: `frontend/src/components/workflow/WorkflowTemplateCanvas.vue`
- Create: `frontend/src/components/workflow/WorkflowCanvasNode.vue`
- Create: `frontend/src/components/workflow/WorkflowCanvasEdge.vue`
- Create: `frontend/src/components/workflow/WorkflowNodeStatusBadge.vue`
- Test: `frontend/test/workflow-template-canvas-surface.test.ts`

**Step 1: Write failing surface test**

Use source checks to assert components exist and include:

- `workflow-template-canvas`
- `workflow-canvas-node`
- `workflow-canvas-edge`
- node click emit
- selected node class
- status badge component

**Step 2: Run test**

Run:

```bash
cd frontend
node --test test/workflow-template-canvas-surface.test.ts
```

Expected: FAIL.

**Step 3: Implement components**

Implement fixed-position rendering:

- Use a relative `.workflow-template-canvas` container.
- Render SVG edges behind nodes.
- Render nodes absolutely by `position`.
- Emit `select-node` on click.
- Use stable sizes so labels do not resize the graph.

**Step 4: Run test**

Run:

```bash
cd frontend
node --test test/workflow-template-canvas-surface.test.ts
```

Expected: PASS.

## Task 6: Build Node Inspector

**Files:**
- Create: `frontend/src/components/workflow/WorkflowNodeInspector.vue`
- Test: `frontend/test/workflow-node-inspector-surface.test.ts`

**Step 1: Write failing test**

Assert the component includes:

- selected node title
- tool selector
- required input section
- run current node button
- task result section
- empty state for no selected node

**Step 2: Run test**

Run:

```bash
cd frontend
node --test test/workflow-node-inspector-surface.test.ts
```

Expected: FAIL.

**Step 3: Implement first inspector shell**

Do not fully duplicate `WorkflowRunPanel` yet. First version should:

- Display node metadata.
- Display available `toolSlugs`.
- Let user choose a tool.
- Display required and produced artifact semantic types.
- Provide a disabled or wired placeholder run button.

**Step 4: Run test**

Run:

```bash
cd frontend
node --test test/workflow-node-inspector-surface.test.ts
```

Expected: PASS.

## Task 7: Integrate Canvas Into Workflow Page

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Test: `frontend/test/workflow-template-page-surface.test.ts`

**Step 1: Write failing test**

Assert `frontend/src/views/workflow/index.vue` imports and uses:

- `WorkflowTemplateCanvas`
- `WorkflowNodeInspector`
- `WORKFLOW_TEMPLATES`

**Step 2: Run test**

Run:

```bash
cd frontend
node --test test/workflow-template-page-surface.test.ts
```

Expected: FAIL.

**Step 3: Integrate page**

Replace the manual mode body with:

- left template/step rail
- center `WorkflowTemplateCanvas`
- right `WorkflowNodeInspector`

Keep the `agent` tab unchanged.

**Step 4: Run tests**

Run:

```bash
cd frontend
node --test test/workflow-template-page-surface.test.ts
node --test test/aidd-agent-surface.test.ts
```

Expected: PASS.

## Task 8: Wire Node Run To Existing Task Flow

**Files:**
- Modify: `frontend/src/components/workflow/WorkflowNodeInspector.vue`
- Modify: `frontend/src/stores/workflow.ts`
- Test: `frontend/test/workflow-node-run-binding.test.ts`

**Step 1: Write failing test**

Assert the inspector emits or calls:

- selected tool update
- node form draft update
- run node event

Assert store has `recordNodeTask`.

**Step 2: Run test**

Run:

```bash
cd frontend
node --test test/workflow-node-run-binding.test.ts
```

Expected: FAIL.

**Step 3: Implement event wiring**

At page level:

- Build task payload from selected node, selected tool, form draft, and artifact bindings.
- Call existing task API through current task creation path.
- Store returned task via `recordNodeTask(nodeId, task)`.

If current task creation logic is tightly coupled to `WorkflowRunPanel`, extract a small helper rather than duplicating request code.

**Step 4: Run tests**

Run:

```bash
cd frontend
node --test test/workflow-node-run-binding.test.ts
node --test test/task-normalization.test.ts
```

Expected: PASS.

## Task 9: Add Artifact Recommendation For Downstream Nodes

**Files:**
- Create: `frontend/src/workflow/template-artifacts.ts`
- Modify: `frontend/src/components/workflow/WorkflowNodeInspector.vue`
- Test: `frontend/test/workflow-template-artifacts.test.ts`

**Step 1: Write failing tests**

Cover:

- Required semantic type matches upstream produced output.
- Latest compatible artifact is preferred.
- Missing artifact returns a clear missing input record.

**Step 2: Run test**

Run:

```bash
cd frontend
node --test test/workflow-template-artifacts.test.ts
```

Expected: FAIL.

**Step 3: Implement artifact helpers**

Add:

```ts
export function resolveNodeInputRequirements(...)
export function recommendArtifactsForNode(...)
```

Use existing artifact types and current artifact store data.

**Step 4: Run test**

Run:

```bash
cd frontend
node --test test/workflow-template-artifacts.test.ts
```

Expected: PASS.

## Task 10: Polish Layout And Responsive Behavior

**Files:**
- Modify: `frontend/src/views/workflow/index.vue`
- Modify: `frontend/src/components/workflow/WorkflowTemplateCanvas.vue`
- Modify: `frontend/src/components/workflow/WorkflowNodeInspector.vue`
- Test: `frontend/test/workflow-template-layout-polish.test.ts`

**Step 1: Write failing surface test**

Assert:

- desktop uses three-column template layout
- small screens stack panels
- canvas has stable min-height
- inspector has scrollable content

**Step 2: Run test**

Run:

```bash
cd frontend
node --test test/workflow-template-layout-polish.test.ts
```

Expected: FAIL.

**Step 3: Implement Less polish**

Use existing variables:

- `@spacing-*`
- `@screen-md`
- `@border-radius-*`
- `@bg-light-secondary`

Avoid text overlap and make node labels truncate cleanly.

**Step 4: Run test and build**

Run:

```bash
cd frontend
node --test test/workflow-template-layout-polish.test.ts
npm run build
```

Expected: PASS and successful build.

## Task 11: Update Documentation

**Files:**
- Modify: `docs/guides/团队协作开发指南.md`
- Create or modify: `docs/guides/工作流节点编排使用指南.md`

**Step 1: Document user workflow**

Explain:

- How to choose a template.
- How to read node statuses.
- How to configure and run a node.
- How upstream artifacts flow to downstream nodes.
- First-version limitations.

**Step 2: Document developer workflow**

Explain:

- Where templates are defined.
- How to add a new template.
- How to add a new node type.
- How to write tests.

**Step 3: Verify docs**

Run:

```bash
grep -n "模板式节点编排" docs/guides/团队协作开发指南.md
grep -n "工作流节点编排" docs/guides/工作流节点编排使用指南.md
```

Expected: both commands find relevant sections.

## Final Verification

Run:

```bash
cd frontend
node --test test/workflow-template-types.test.ts
node --test test/workflow-templates.test.ts
node --test test/workflow-template-state.test.ts
node --test test/workflow-template-session.test.ts
node --test test/workflow-template-canvas-surface.test.ts
node --test test/workflow-node-inspector-surface.test.ts
node --test test/workflow-template-page-surface.test.ts
node --test test/workflow-node-run-binding.test.ts
node --test test/workflow-template-artifacts.test.ts
node --test test/workflow-template-layout-polish.test.ts
npm run build
```

Expected:

- All listed `node --test` commands pass.
- `npm run build` exits with code 0.
- `/workflow` still has both template/manual workflow mode and agent mode available according to the chosen UI labels.
