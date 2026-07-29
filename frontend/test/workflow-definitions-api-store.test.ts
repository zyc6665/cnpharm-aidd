import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

function readSource(relativePath: string): string {
  return readFileSync(resolve(relativePath), 'utf8')
}

test('workflow definition api exposes CRUD methods on /workflows', () => {
  assert.equal(existsSync(resolve('src/api/workflows.ts')), true)
  const source = readSource('src/api/workflows.ts')

  for (const marker of [
    'getWorkflowDefinitions',
    'createWorkflowDefinition',
    'updateWorkflowDefinition',
    'deleteWorkflowDefinition',
    "'/workflows'"
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }
})

test('workflow definitions store tracks list, current definition and persistence actions', () => {
  assert.equal(existsSync(resolve('src/stores/workflow-definitions.ts')), true)
  const source = readSource('src/stores/workflow-definitions.ts')
  const storeIndex = readSource('src/stores/index.ts')
  const apiIndex = readSource('src/api/index.ts')

  for (const marker of [
    'useWorkflowDefinitionsStore',
    'currentWorkflowDefinition',
    'fetchWorkflowDefinitions',
    'saveWorkflowDefinition',
    'loadWorkflowDefinition',
    'removeWorkflowDefinition'
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }

  assert.equal(storeIndex.includes("export { useWorkflowDefinitionsStore }"), true)
  assert.equal(apiIndex.includes("export * from './workflows'"), true)
})

test('workflow definitions list loading degrades without blanking the workbench', () => {
  const store = readSource('src/stores/workflow-definitions.ts')
  const page = readSource('src/views/workflow/index.vue')

  assert.equal(store.includes('workflowDefinitions.value = []'), true)
  assert.equal(store.includes('return {'), true)
  assert.equal(page.includes('Promise.allSettled'), true)
})
