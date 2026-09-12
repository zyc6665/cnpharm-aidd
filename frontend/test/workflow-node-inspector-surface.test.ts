import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

function readInspectorSources() {
  return [
    'WorkflowNodeInspector.vue',
    'NodeToolPanel.vue',
    'NodeEdgePanel.vue',
    'NodeResultPanel.vue'
  ].map(file => readFileSync(resolve(`src/components/workflow/${file}`), 'utf8')).join('\n')
}

test('workflow node inspector exposes node configuration sections', () => {
  const file = resolve('src/components/workflow/WorkflowNodeInspector.vue')
  assert.equal(existsSync(file), true)

  const source = readInspectorSources()
  for (const marker of [
    'workflow-node-inspector',
    "workflow.inspector.toolSelector",
    "workflow.inspector.requiredInput",
    "workflow.inspector.upstreamEdge",
    "workflow.inspector.runWorkflow",
    "workflow.inspector.taskResult",
    "workflow.inspector.noSelectedNode"
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }
})

test('workflow node inspector does not pass null image to ant empty', () => {
  const source = readInspectorSources()

  assert.equal(source.includes(':image="null"'), false)
})

test('workflow node inspector uses real available tools and can add edges', () => {
  const source = readInspectorSources()

  assert.equal(source.includes('availableTools'), true)
  assert.equal(source.includes('toolOptions'), true)
  assert.equal(source.includes("event: 'add-edge'"), true)
  assert.equal(source.includes('sourceNodeOptions'), true)
  assert.equal(source.includes('WORKFLOW_ARTIFACT_SEMANTIC_TYPES'), true)
})

test('workflow node inspector embeds a real node run panel', () => {
  const inspectorSource = readInspectorSources()
  const runPanelPath = resolve('src/components/workflow/WorkflowNodeRunPanel.vue')

  assert.equal(existsSync(runPanelPath), true)
  const runPanelSource = readFileSync(runPanelPath, 'utf8')

  for (const marker of [
    'WorkflowNodeRunPanel',
    'selected-tool-slug',
    'node-id'
  ]) {
    assert.equal(inspectorSource.includes(marker), true, `inspector missing ${marker}`)
  }

  for (const marker of [
    'ToolRunInputForm',
    'buildToolFormInitialState',
    'getToolDetail',
    'flattenToolInputSchema',
    ':allow-uploads="true"'
  ]) {
    assert.equal(runPanelSource.includes(marker), true, `run panel missing ${marker}`)
  }

  for (const marker of [
    'buildTaskSubmissionPayload',
    'uploadFile',
    'recordNodeTask',
    'pollTaskUntilTerminal'
  ]) {
    assert.equal(runPanelSource.includes(marker), false, `run panel should not include ${marker}`)
  }
})

test('workflow node inspector groups details into tabs', () => {
  const source = readInspectorSources()

  for (const marker of [
    'inspector-detail-tabs',
    'key="config"',
    'key="dependencies"',
    'key="results"',
    "workflow.inspector.configTab",
    "workflow.inspector.dependenciesTab",
    "workflow.inspector.resultsTab"
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }
})

test('workflow node inspector exposes compatible edge suggestions', () => {
  const source = readInspectorSources()

  for (const marker of [
    'suggestWorkflowEdgesForNode',
    'edgeSuggestions',
    "workflow.inspector.recommendedEdges",
    "workflow.inspector.addEdge",
    'addSuggestedEdge'
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }
})

test('workflow node inspector split surfaces use semantic theme backgrounds', () => {
  const componentSources = new Map(
    ['WorkflowNodeInspector.vue', 'WorkflowNodeRunPanel.vue', 'WorkflowNodeStatusBadge.vue'].map(
      file => [file, readFileSync(resolve(`src/components/workflow/${file}`), 'utf8')]
    )
  )

  for (const [file, source] of componentSources) {
    assert.equal(source.includes('rgba(255, 255, 255'), false, `${file} uses a light-only surface`)
  }

  for (const file of ['WorkflowNodeRunPanel.vue', 'WorkflowNodeStatusBadge.vue']) {
    assert.equal(
      componentSources.get(file)?.includes('background: @bg-elevated'),
      true,
      `${file} is missing the semantic elevated surface`
    )
  }
})
