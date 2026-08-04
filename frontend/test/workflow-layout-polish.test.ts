import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

function readSource(relativePath: string): string {
  return readFileSync(resolve(relativePath), 'utf8')
}

test('workflow node inspector exposes researcher-facing node actions', () => {
  const inspectorSource = readSource('src/components/workflow/WorkflowNodeInspector.vue')
  const resultSource = readSource('src/components/workflow/NodeResultPanel.vue')
  const pageSource = readSource('src/views/workflow/index.vue')

  for (const marker of [
    'workflow.inspector.runWorkflow',
    'workflow.inspector.viewTaskDetail',
    'workflow.inspector.outputFiles',
    "event: 'run-node'",
    "emit('view-task-detail'"
  ]) {
    assert.equal((inspectorSource + resultSource).includes(marker), true, `missing ${marker}`)
  }

  for (const marker of [
    'handleRunWorkflowDefinition',
    'handleViewTaskDetail',
    '@run-node="handleRunWorkflowDefinition"',
    '@view-task-detail="handleViewTaskDetail"'
  ]) {
    assert.equal(pageSource.includes(marker), true, `missing ${marker}`)
  }

  const executionSource = readSource('src/composables/useWorkflowExecution.ts')
  assert.equal(executionSource.includes('per-node Task scheduling logic'), true)
  assert.equal(executionSource.includes('async function runDownstreamFrom'), false)
})

test('workflow tool palette exposes multi-dimensional tool filters', () => {
  const paletteSource = readSource('src/components/workflow/WorkflowToolPalette.vue')
  const canvasSource = readSource('src/composables/useWorkflowCanvas.ts')
  const pageSource = readSource('src/views/workflow/index.vue')

  for (const marker of [
    'workflow.palette.filterStage',
    'workflow.palette.filterInput',
    'workflow.palette.filterOutput',
    'workflow.palette.filterExecutor',
    'stageOptions',
    'inputOptions',
    'outputOptions',
    'executorOptions'
  ]) {
    assert.equal(paletteSource.includes(marker), true, `missing ${marker}`)
  }

  for (const marker of [
    'sidebarStageFilter',
    'sidebarInputFilter',
    'sidebarOutputFilter',
    'sidebarExecutorFilter'
  ]) {
    assert.equal(canvasSource.includes(marker), true, `missing ${marker}`)
  }

  for (const marker of [
    ':stage-options="sidebarStageOptions"',
    ':input-options="sidebarInputOptions"',
    ':output-options="sidebarOutputOptions"',
    ':executor-options="sidebarExecutorOptions"'
  ]) {
    assert.equal(pageSource.includes(marker), true, `missing ${marker}`)
  }
})
