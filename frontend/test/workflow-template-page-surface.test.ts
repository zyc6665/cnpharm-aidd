import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const source = readFileSync(resolve('src/views/workflow/index.vue'), 'utf8')

test('workflow page mounts template canvas and inspector in manual mode', () => {
  for (const marker of [
    'WorkflowTemplateCanvas',
    'WorkflowNodeInspector',
    'WORKFLOW_TEMPLATES',
    'getWorkflowTemplateById',
    'workflow-template-layout',
    'template-step-rail'
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
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
    'resolveNodeStatusReason',
    'workflow-sidebar-tool-library',
    'sidebarToolSearchKeyword',
    'filteredSidebarToolOptions',
    '运行可执行节点',
    '保存',
    '加载'
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }
})

test('workflow page exposes workflow result report integration', () => {
  for (const marker of [
    'WorkflowResultsReportPanel',
    'workflow-results-region',
    'workflowReportRows'
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }
})

test('workflow page keeps agent mode available', () => {
  assert.equal(source.includes('<AiddAgentPanel />'), true)
  assert.equal(source.includes("key=\"agent\""), true)
})
