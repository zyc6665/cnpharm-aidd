import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const source = readFileSync(resolve('src/workflow/canvas-types.ts'), 'utf8')

test('workflow template model exposes graph primitives', () => {
  assert.equal(source.includes('WorkflowCanvasPreset'), true)
  assert.equal(source.includes('WorkflowCanvasNode'), true)
  assert.equal(source.includes('WorkflowCanvasEdge'), true)
  assert.equal(source.includes('position'), true)
})
