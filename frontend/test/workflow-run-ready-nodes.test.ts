import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { resolveReadyToolNodeIds, resolveWorkflowExecutionOrder } from '../src/workflow/canvas-runner.ts'
import type { WorkflowCanvasPreset } from '../src/workflow/canvas-types.ts'

const template: WorkflowCanvasPreset = {
  id: 'aidd-template',
  kind: 'aidd',
  nameKey: 'workflow.template',
  nodes: [
    { id: 'input', type: 'input', titleKey: 'input', position: { x: 0, y: 0 } },
    {
      id: 'ready-tool',
      type: 'tool',
      titleKey: 'ready',
      position: { x: 160, y: 0 },
      toolSlugs: ['tool-a']
    },
    {
      id: 'blocked-tool',
      type: 'tool',
      titleKey: 'blocked',
      position: { x: 320, y: 0 },
      toolSlugs: ['tool-b']
    }
  ],
  edges: []
}

test('resolveReadyToolNodeIds returns only tool nodes currently marked ready', () => {
  assert.deepEqual(
    resolveReadyToolNodeIds({
      template,
      nodeStatuses: {
        input: 'completed',
        'ready-tool': 'ready',
        'blocked-tool': 'idle'
      }
    }),
    ['ready-tool']
  )
})

test('resolveWorkflowExecutionOrder sorts ready tool nodes by graph dependencies', () => {
  const dependentTemplate: WorkflowCanvasPreset = {
    ...template,
    nodes: [
      { id: 'input', type: 'input', titleKey: 'input', position: { x: 0, y: 0 } },
      {
        id: 'third',
        type: 'tool',
        titleKey: 'third',
        position: { x: 320, y: 0 },
        toolSlugs: ['tool-c']
      },
      {
        id: 'first',
        type: 'tool',
        titleKey: 'first',
        position: { x: 120, y: 0 },
        toolSlugs: ['tool-a']
      },
      {
        id: 'second',
        type: 'tool',
        titleKey: 'second',
        position: { x: 220, y: 0 },
        toolSlugs: ['tool-b']
      }
    ],
    edges: [
      { id: 'edge-input-first', source: 'input', target: 'first' },
      { id: 'edge-first-second', source: 'first', target: 'second' },
      { id: 'edge-second-third', source: 'second', target: 'third' }
    ]
  }

  assert.deepEqual(
    resolveWorkflowExecutionOrder({
      template: dependentTemplate,
      candidateNodeIds: ['third', 'first', 'second']
    }),
    ['first', 'second', 'third']
  )
})

test('workflow page exposes save, load and run-ready controls', () => {
  const source = readFileSync(resolve('src/views/workflow/index.vue'), 'utf8')
  const runsStore = readFileSync(resolve('src/stores/workflow-runs.ts'), 'utf8')

  for (const marker of [
    'handleSaveWorkflow',
    'handleLoadWorkflow',
    'handleRunWorkflowDefinition',
    'workflow-definition-bar'
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }

  assert.equal(runsStore.includes('runWorkflowDefinition'), true)
  assert.equal(runsStore.includes('createWorkflowRun'), true)
})

test('workflow page uses editable graph for canvas, save, edges, and available tools', () => {
  const source = readFileSync(resolve('src/views/workflow/index.vue'), 'utf8')
  const canvas = readFileSync(resolve('src/composables/useWorkflowCanvas.ts'), 'utf8')

  for (const marker of [
    'editableCanvasPreset',
    'availableWorkflowTools',
    'handleAddToolNode',
    'handleDeleteNode',
    'handleAddEdge',
    '@add-edge="handleAddEdge"',
    'toolsStore.fetchWorkflowTools'
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }

  assert.equal(canvas.includes('workflowStore.canvasNodes'), true)
  assert.equal(canvas.includes('workflowStore.canvasEdges'), true)
  assert.equal(canvas.includes('workflowStore.hasCanvasOverride'), true)
})
