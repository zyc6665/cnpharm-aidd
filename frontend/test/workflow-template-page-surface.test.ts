import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const pageSource = readFileSync(resolve('src/views/workflow/index.vue'), 'utf8')
const canvasSource = readFileSync(resolve('src/composables/useWorkflowCanvas.ts'), 'utf8')
const paletteSource = readFileSync(resolve('src/components/workflow/WorkflowToolPalette.vue'), 'utf8')

test('workflow page mounts template canvas and inspector in manual mode', () => {
  for (const marker of [
    'WorkflowTemplateCanvas',
    'WorkflowNodeInspector',
    'useWorkflowCanvas',
    'workflow-template-layout',
    'template-step-rail'
  ]) {
    assert.equal(pageSource.includes(marker), true, `missing ${marker}`)
  }

  for (const marker of [
    'WORKFLOW_TEMPLATES',
    'getWorkflowTemplateById',
    'buildCurrentWorkflowDefinition',
    'resolveNodeStatusReason'
  ]) {
    assert.equal(canvasSource.includes(marker), true, `missing ${marker}`)
  }
})

test('workflow page exposes a sidebar tool library and run summary', () => {
  for (const marker of [
    'workflow-status-summary',
    'readyNodeCount',
    'blockedNodeCount',
    'runningNodeCount',
    'completedNodeCount',
    'failedNodeCount',
    'WorkflowToolPalette',
    '运行可执行节点',
    '保存',
    '加载'
  ]) {
    assert.equal(pageSource.includes(marker), true, `missing ${marker}`)
  }

  for (const marker of [
    'sidebarToolSearchKeyword',
    'filteredSidebarToolOptions',
    'availableWorkflowTools',
    'readyNodeCount',
    'blockedNodeCount',
    'runningNodeCount',
    'completedNodeCount',
    'failedNodeCount'
  ]) {
    assert.equal(canvasSource.includes(marker), true, `missing ${marker}`)
  }

  assert.equal(paletteSource.includes('workflow-sidebar-tool-library'), true)
})

test('workflow page exposes workflow result report integration', () => {
  for (const marker of [
    'WorkflowResultsReportPanel',
    'workflow-results-region',
    'workflowReportRows'
  ]) {
    assert.equal(pageSource.includes(marker), true, `missing ${marker}`)
  }
})

test('workflow page keeps agent mode available', () => {
  assert.equal(pageSource.includes('<AiddAgentPanel />'), true)
  assert.equal(pageSource.includes("key=\"agent\""), true)
})
