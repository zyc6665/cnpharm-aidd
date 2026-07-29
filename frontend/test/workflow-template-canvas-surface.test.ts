import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

function readSource(relativePath: string): string {
  return readFileSync(resolve(relativePath), 'utf8')
}

test('workflow template canvas components exist', () => {
  for (const file of [
    'src/components/workflow/WorkflowTemplateCanvas.vue',
    'src/components/workflow/WorkflowCanvasNode.vue',
    'src/components/workflow/WorkflowCanvasEdge.vue',
    'src/components/workflow/WorkflowNodeStatusBadge.vue'
  ]) {
    assert.equal(existsSync(resolve(file)), true, `missing ${file}`)
  }
})

test('workflow template canvas exposes graph interaction surface', () => {
  const canvas = readSource('src/components/workflow/WorkflowTemplateCanvas.vue')
  const node = readSource('src/components/workflow/WorkflowCanvasNode.vue')
  const edge = readSource('src/components/workflow/WorkflowCanvasEdge.vue')
  const badge = readSource('src/components/workflow/WorkflowNodeStatusBadge.vue')

  assert.equal(canvas.includes('workflow-template-canvas'), true)
  assert.equal(canvas.includes('WorkflowCanvasNode'), true)
  assert.equal(canvas.includes('WorkflowCanvasEdge'), true)
  assert.equal(canvas.includes('select-node'), true)
  assert.equal(node.includes('workflow-canvas-node'), true)
  assert.equal(node.includes('is-selected'), true)
  assert.equal(edge.includes('workflow-canvas-edge'), true)
  assert.equal(badge.includes('workflow-node-status-badge'), true)
})

test('workflow template canvas stays focused on the graph surface', () => {
  const canvas = readSource('src/components/workflow/WorkflowTemplateCanvas.vue')

  assert.equal(canvas.includes('canvas-viewport'), true)
  assert.equal(canvas.includes('canvas-surface'), true)
  assert.equal(canvas.includes('canvas-tool-library'), false)
  assert.equal(canvas.includes('filteredToolOptions'), false)
})
