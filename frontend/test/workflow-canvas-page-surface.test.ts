import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const pageSource = readFileSync(resolve('src/views/workflow/index.vue'), 'utf8')
const canvasSource = readFileSync(resolve('src/composables/useWorkflowCanvas.ts'), 'utf8')
const persistenceSource = readFileSync(resolve('src/composables/useWorkflowPersistence.ts'), 'utf8')
const paletteSource = readFileSync(resolve('src/components/workflow/WorkflowToolPalette.vue'), 'utf8')
const railSource = readFileSync(resolve('src/components/workflow/WorkflowWorkbenchRail.vue'), 'utf8')
const shellSource = readFileSync(resolve('src/components/workflow/WorkflowWorkbenchShell.vue'), 'utf8')
const headerSource = readFileSync(resolve('src/components/workflow/WorkflowWorkbenchHeader.vue'), 'utf8')
const runDetailSource = readFileSync(resolve('src/views/workflow/RunDetail.vue'), 'utf8')

test('workflow page mounts template canvas and inspector in manual mode', () => {
  for (const marker of [
    'WorkflowCanvasBoard',
    'WorkflowNodeInspector',
    'useWorkflowCanvas',
    'WorkflowWorkbenchShell',
    'WorkflowWorkbenchRail'
  ]) {
    assert.equal(pageSource.includes(marker), true, `missing ${marker}`)
  }

  assert.equal(shellSource.includes('ResizableWorkbenchSidebar'), true)

  for (const marker of [
    'WORKFLOW_CANVAS_PRESETS',
    'getWorkflowCanvasPresetById',
    'buildCurrentWorkflowDefinition',
    'resolveNodeStatusReason'
  ]) {
    assert.equal(canvasSource.includes(marker), true, `missing ${marker}`)
  }
})

test('workflow page exposes a sidebar tool library and run summary', () => {
  for (const marker of [
    'readyNodeCount',
    'blockedNodeCount',
    'runningNodeCount',
    'completedNodeCount',
    'failedNodeCount',
    'handleRunWorkflowDefinition',
    'WorkflowPreflightPanel'
  ]) {
    assert.equal(pageSource.includes(marker), true, `missing ${marker}`)
  }

  assert.equal(railSource.includes('workflow-status-summary'), true)
  assert.equal(railSource.includes('WorkflowToolPalette'), true)
  assert.equal(shellSource.includes('WorkflowWorkbenchHeader'), true)

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
    'WorkflowResultsSidebar',
    'workflowReportRows'
  ]) {
    assert.equal(pageSource.includes(marker), true, `missing ${marker}`)
  }
})

test('workflow page keeps agent mode available', () => {
  assert.equal(pageSource.includes('AiddAgentPanel'), true)
  assert.equal(pageSource.includes("key=\"agent\""), true)
})

test('workflow page and run detail user-facing copy should use locale keys', () => {
  for (const marker of [
    'workflow.definition.save',
    'workflow.definition.load',
    'workflow.definition.projectScoped',
    'workflow.definition.startFullRun'
  ]) {
    assert.equal(pageSource.includes(marker), true, `missing ${marker}`)
  }

  for (const literal of ['保存', '加载', '项目工作流', '运行工作流']) {
    assert.equal(pageSource.includes(literal), false, `hardcoded workflow page literal: ${literal}`)
  }

  for (const marker of [
    'workflow.runDetail.title',
    'workflow.runDetail.subtitle',
    'workflow.runDetail.canceled',
    'workflow.runDetail.nodeRetried'
  ]) {
    assert.equal(runDetailSource.includes(marker), true, `missing ${marker}`)
  }

  for (const literal of [
    '工作流运行详情',
    '查看运行节点、任务和错误状态',
    '工作流运行已取消',
    '工作流节点已重试'
  ]) {
    assert.equal(runDetailSource.includes(literal), false, `hardcoded run detail literal: ${literal}`)
  }
})

test('workflow workbench chrome status copy should use locale keys', () => {
  for (const marker of [
    'workflow.workbenchHeader.kicker',
    'workflow.workbenchHeader.titleFallback',
    'workflow.statusSummary.ready',
    'workflow.statusSummary.blocked',
    'workflow.statusSummary.running',
    'workflow.statusSummary.completed',
    'workflow.statusSummary.failed'
  ]) {
    assert.equal(
      railSource.includes(marker) || headerSource.includes(marker),
      true,
      `missing ${marker}`
    )
  }

  for (const literal of ['工作流工作台', '未命名工作流', '可运行', '阻塞', '运行中', '完成', '失败']) {
    assert.equal(railSource.includes(literal), false, `hardcoded rail literal: ${literal}`)
    assert.equal(headerSource.includes(literal), false, `hardcoded header literal: ${literal}`)
  }
})

test('agent draft reuses persisted definition mapping and resets saved identity', () => {
  for (const marker of [
    'applyWorkflowDraft',
    'mapWorkflowDefinitionToCanvasPayload',
    'workflowDefinitionsStore.clearCurrentWorkflowDefinition()',
    'workflowRunInputSelections.value = { ...draft.input_files }',
    'producedOutputTypes',
    'selected_tool_by_node'
  ]) {
    assert.equal(persistenceSource.includes(marker), true, `missing ${marker}`)
  }
})
