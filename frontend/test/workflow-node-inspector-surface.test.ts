import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

test('workflow node inspector exposes node configuration sections', () => {
  const file = resolve('src/components/workflow/WorkflowNodeInspector.vue')
  assert.equal(existsSync(file), true)

  const source = readFileSync(file, 'utf8')
  for (const marker of [
    'workflow-node-inspector',
    'tool selector',
    'required input',
    'upstream edge',
    'run current node',
    'task result',
    'no selected node'
  ]) {
    assert.equal(source.toLowerCase().includes(marker), true, `missing ${marker}`)
  }
})

test('workflow node inspector does not pass null image to ant empty', () => {
  const source = readFileSync(resolve('src/components/workflow/WorkflowNodeInspector.vue'), 'utf8')

  assert.equal(source.includes(':image="null"'), false)
})

test('workflow node inspector uses real available tools and can add edges', () => {
  const source = readFileSync(resolve('src/components/workflow/WorkflowNodeInspector.vue'), 'utf8')

  assert.equal(source.includes('availableTools'), true)
  assert.equal(source.includes('toolOptions'), true)
  assert.equal(source.includes("event: 'add-edge'"), true)
  assert.equal(source.includes('sourceNodeOptions'), true)
  assert.equal(source.includes('WORKFLOW_ARTIFACT_SEMANTIC_TYPES'), true)
})

test('workflow node inspector embeds a real node run panel', () => {
  const inspectorSource = readFileSync(resolve('src/components/workflow/WorkflowNodeInspector.vue'), 'utf8')
  const runPanelPath = resolve('src/components/workflow/WorkflowNodeRunPanel.vue')

  assert.equal(existsSync(runPanelPath), true)
  const runPanelSource = readFileSync(runPanelPath, 'utf8')

  for (const marker of [
    'WorkflowNodeRunPanel',
    'selected-tool-slug',
    'node-id',
    'task-submitted'
  ]) {
    assert.equal(inspectorSource.includes(marker), true, `inspector missing ${marker}`)
  }

  for (const marker of [
    'ArtifactFilePicker',
    'buildTaskSubmissionPayload',
    'buildToolFormInitialState',
    'getToolDetail',
    'uploadFile',
    'recordNodeTask',
    'pollTaskUntilTerminal'
  ]) {
    assert.equal(runPanelSource.includes(marker), true, `run panel missing ${marker}`)
  }
})

test('workflow node inspector groups details into tabs', () => {
  const source = readFileSync(resolve('src/components/workflow/WorkflowNodeInspector.vue'), 'utf8')

  for (const marker of [
    'inspector-detail-tabs',
    'key=\"config\"',
    'key=\"dependencies\"',
    'key=\"results\"',
    '配置',
    '依赖',
    '结果'
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }
})

test('workflow node inspector exposes compatible edge suggestions', () => {
  const source = readFileSync(resolve('src/components/workflow/WorkflowNodeInspector.vue'), 'utf8')

  for (const marker of [
    'suggestWorkflowEdgesForNode',
    'edgeSuggestions',
    '推荐连线',
    '添加连线',
    'handleAddSuggestedEdge'
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }
})
