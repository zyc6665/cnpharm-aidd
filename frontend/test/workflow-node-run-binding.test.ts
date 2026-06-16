import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const workflowPage = readFileSync(resolve('src/views/workflow/index.vue'), 'utf8')
const inspector = readFileSync(resolve('src/components/workflow/WorkflowNodeInspector.vue'), 'utf8')
const store = readFileSync(resolve('src/stores/workflow.ts'), 'utf8')

test('workflow page binds run-node to existing task creation flow', () => {
  for (const marker of [
    'useTasksStore',
    'tasksStore.createTask',
    'workflowStore.recordNodeTask',
    'resolveToolForNode',
    'handleRunNode'
  ]) {
    assert.equal(workflowPage.includes(marker), true, `missing ${marker}`)
  }
})

test('node inspector emits tool selection and run events', () => {
  assert.equal(inspector.includes("event: 'select-tool'"), true)
  assert.equal(inspector.includes("event: 'run-node'"), true)
  assert.equal(inspector.includes("Run current node"), true)
})

test('workflow store can record node tasks', () => {
  assert.equal(store.includes('recordNodeTask'), true)
})
