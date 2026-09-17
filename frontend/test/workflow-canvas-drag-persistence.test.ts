import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

function readSource(relativePath: string): string {
  return readFileSync(resolve(relativePath), 'utf8')
}

test('workflow session stores node position overrides for canvas persistence', () => {
  const source = readSource('src/stores/workflow.ts')

  assert.equal(source.includes('canvasNodes'), true)
  assert.equal(source.includes('canvasEdges'), true)
  assert.equal(source.includes('ensureCanvasFromPreset'), true)
  assert.equal(source.includes('addToolNode'), true)
  assert.equal(source.includes('deleteCanvasNode'), true)
  assert.equal(source.includes('addCanvasEdge'), true)
  assert.equal(source.includes('deleteCanvasEdge'), true)
  assert.equal(source.includes('nodePositionById'), true)
  assert.equal(source.includes('moveNode'), true)
  assert.equal(source.includes('setNodePositions'), true)
  assert.equal(source.includes('applyWorkflowDefinition'), true)
})

test('workflow page normalizes persisted workflow session before rendering records', () => {
  const store = readSource('src/stores/workflow.ts')
  const session = readSource('src/stores/workflow-session.ts')
  const page = readSource('src/views/workflow/index.vue')

  assert.equal(store.includes('normalizeSessionShape'), true)
  assert.equal(session.includes('isPlainRecord'), true)
  assert.equal(page.includes('workflowStore.normalizeSessionShape()'), true)
})

test('template canvas renders resolved node positions and emits move-node', () => {
  const canvas = readSource('src/components/workflow/WorkflowCanvasBoard.vue')
  const node = readSource('src/components/workflow/WorkflowCanvasPanelNode.vue')

  assert.equal(canvas.includes('nodePositions'), true)
  assert.equal(canvas.includes('resolvedNodes'), true)
  assert.equal(canvas.includes("event: 'move-node'"), true)
  assert.equal(canvas.includes("event: 'add-tool-node'"), true)
  assert.equal(canvas.includes("event: 'delete-node'"), true)
  assert.equal(canvas.includes('availableTools'), false)
  assert.equal(node.includes("event: 'delete-node'"), true)
  assert.equal(node.includes('@pointerdown'), true)
  assert.equal(node.includes("event: 'move-node'"), true)
})

test('workflow graph maintenance exposes edge deletion and semantic sync', () => {
  const store = readSource('src/stores/workflow.ts')
  const canvasStore = readSource('src/stores/workflow-canvas.ts')
  const inspector = readSource('src/components/workflow/WorkflowNodeInspector.vue')
  const edgePanel = readSource('src/components/workflow/NodeEdgePanel.vue')

  for (const marker of ['deleteCanvasEdge', 'syncCanvasNodeSemanticTypes']) {
    assert.equal(store.includes(marker), true, `store missing ${marker}`)
  }

  for (const marker of ['requiredInputTypes', 'producedOutputTypes']) {
    assert.equal(canvasStore.includes(marker), true, `canvas store missing ${marker}`)
  }

  assert.equal(inspector.includes('NodeEdgePanel'), true)
  assert.equal(inspector.includes('@delete-edge="$emit(\'delete-edge\', $event)"'), true)

  for (const marker of ["event: 'delete-edge'", "t('workflow.inspector.deleteEdge')"]) {
    assert.equal(edgePanel.includes(marker), true, `edge panel missing ${marker}`)
  }
})
