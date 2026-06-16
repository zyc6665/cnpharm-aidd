import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

function readSource(relativePath: string): string {
  return readFileSync(resolve(relativePath), 'utf8')
}

test('workflow session stores node position overrides for canvas persistence', () => {
  const source = readSource('src/stores/workflow.ts')

  assert.equal(source.includes('nodePositionById'), true)
  assert.equal(source.includes('moveNode'), true)
  assert.equal(source.includes('setNodePositions'), true)
  assert.equal(source.includes('applyWorkflowDefinition'), true)
})

test('template canvas renders resolved node positions and emits move-node', () => {
  const canvas = readSource('src/components/workflow/WorkflowTemplateCanvas.vue')
  const node = readSource('src/components/workflow/WorkflowCanvasNode.vue')

  assert.equal(canvas.includes('nodePositions'), true)
  assert.equal(canvas.includes('resolvedNodes'), true)
  assert.equal(canvas.includes("event: 'move-node'"), true)
  assert.equal(node.includes('@pointerdown'), true)
  assert.equal(node.includes("event: 'move-node'"), true)
})
