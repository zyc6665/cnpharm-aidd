import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const workflowPage = readFileSync(resolve('src/views/workflow/index.vue'), 'utf8')
const canvas = readFileSync(resolve('src/components/workflow/WorkflowTemplateCanvas.vue'), 'utf8')
const inspector = readFileSync(resolve('src/components/workflow/WorkflowNodeInspector.vue'), 'utf8')

test('workflow template layout keeps desktop three-column structure', () => {
  assert.equal(workflowPage.includes('grid-template-columns: minmax(220px, 260px) minmax(0, 1fr) minmax(300px, 360px);'), true)
  assert.equal(workflowPage.includes('@media (max-width: @screen-md)'), true)
})

test('workflow canvas reserves stable surface height', () => {
  assert.equal(canvas.includes('min-height: 560px;'), true)
  assert.equal(canvas.includes('background-size: 28px 28px;'), true)
})

test('workflow inspector stays scrollable on compact screens', () => {
  assert.equal(inspector.includes('max-height:720px;'), true)
  assert.equal(inspector.includes('overflow:auto;'), true)
})
