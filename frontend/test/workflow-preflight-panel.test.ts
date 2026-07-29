import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

test('workflow preflight panel component renders summary, issues, and run action', () => {
  const componentPath = resolve('src/components/workflow/WorkflowPreflightPanel.vue')

  assert.equal(existsSync(componentPath), true)

  const source = readFileSync(componentPath, 'utf8')
  for (const marker of [
    "workflow.preflight.title",
    'preflight.primaryMessage',
    'preflight.issues',
    'preflight.canRun',
    'run-ready-nodes',
    "workflow.preflight.viewNode",
    "workflow.preflight.runReadyNodes"
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }
})

test('workflow page integrates preflight summary before the canvas', () => {
  const source = readFileSync(resolve('src/views/workflow/index.vue'), 'utf8')

  for (const marker of [
    'WorkflowPreflightPanel',
    'workflowPreflight',
    'buildWorkflowPreflight',
    'workflow-preflight-region',
    '@run-ready-nodes="handleRunReadyNodes"',
    '@select-node="workflowStore.setActiveNode"'
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }
})
