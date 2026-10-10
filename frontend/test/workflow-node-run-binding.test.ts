import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const workflowPage = readFileSync(resolve('src/views/workflow/index.vue'), 'utf8')
const inspector = readFileSync(resolve('src/components/workflow/WorkflowNodeInspector.vue'), 'utf8')
const resultPanel = readFileSync(resolve('src/components/workflow/NodeResultPanel.vue'), 'utf8')
const store = readFileSync(resolve('src/stores/workflow.ts'), 'utf8')
const execution = readFileSync(resolve('src/composables/useWorkflowExecution.ts'), 'utf8')

test('workflow page routes run-node through WorkflowRun creation', () => {
  for (const marker of ['handleRunWorkflowDefinition', '@run-ready-nodes="handleRunWorkflowDefinition"']) {
    assert.equal(workflowPage.includes(marker), true, `missing ${marker}`)
  }

  for (const marker of [
    'useTasksStore',
    'handleRunNode'
  ]) {
    assert.equal(workflowPage.includes(marker), false, `page should not include ${marker}`)
  }

  assert.equal(execution.includes('per-node Task scheduling logic'), true)
  assert.equal(execution.includes('tasksStore.createTask'), false)
})

test('node inspector emits tool selection and run events', () => {
  assert.equal(inspector.includes("event: 'select-tool'"), true)
  assert.equal(inspector.includes("event: 'view-task-detail'"), true)
  assert.equal(resultPanel.includes("t('workflow.inspector.viewTaskDetail')"), true)
})

test('workflow store can record node tasks', () => {
  assert.equal(store.includes('recordNodeTask'), true)
})
