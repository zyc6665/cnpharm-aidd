import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

function readSource(relativePath: string): string {
  return readFileSync(resolve(relativePath), 'utf8')
}

test('workflow template canvas components exist', () => {
  for (const file of [
    'src/components/workflow/WorkflowCanvasBoard.vue',
    'src/components/workflow/WorkflowCanvasPanelNode.vue',
    'src/components/workflow/WorkflowCanvasEdge.vue',
    'src/components/workflow/WorkflowNodeStatusBadge.vue'
  ]) {
    assert.equal(existsSync(resolve(file)), true, `missing ${file}`)
  }

  assert.equal(existsSync(resolve('src/components/workflow/WorkflowCanvasNode.vue')), false)
})

test('workflow template canvas exposes graph interaction surface', () => {
  const canvas = readSource('src/components/workflow/WorkflowCanvasBoard.vue')
  const node = readSource('src/components/workflow/WorkflowCanvasPanelNode.vue')
  const edge = readSource('src/components/workflow/WorkflowCanvasEdge.vue')
  const badge = readSource('src/components/workflow/WorkflowNodeStatusBadge.vue')

  assert.equal(canvas.includes('workflow-canvas-board'), true)
  assert.equal(canvas.includes('WorkflowCanvasPanelNode'), true)
  assert.equal(canvas.includes('WorkflowCanvasEdge'), true)
  assert.equal(canvas.includes('select-node'), true)
  assert.equal(node.includes('workflow-canvas-panel-node'), true)
  assert.equal(node.includes('is-selected'), true)
  assert.equal(edge.includes('workflow-canvas-edge'), true)
  assert.equal(badge.includes('workflow-node-status-badge'), true)
})

test('workflow template canvas stays focused on the graph surface', () => {
  const canvas = readSource('src/components/workflow/WorkflowCanvasBoard.vue')

  assert.equal(canvas.includes('canvas-viewport'), true)
  assert.equal(canvas.includes('canvas-surface'), true)
  assert.equal(canvas.includes('canvas-tool-library'), false)
  assert.equal(canvas.includes('filteredToolOptions'), false)
})
