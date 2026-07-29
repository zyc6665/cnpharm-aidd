import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工作台中栏应挂载轻量结果面板并保留查看完整详情入口', () => {
  const source = readSource('src/components/workflow/WorkflowRunPanel.vue')

  assert.equal(source.includes('WorkflowTaskResultPanel'), true)
  assert.equal(source.includes('resultTaskId'), true)
  assert.equal(source.includes('resultTaskSummary'), true)
})

test('任务详情页应复用共享输出摘要和日志预览组件', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/TaskOutputSummary.vue')), true)
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/TaskLogPreview.vue')), true)

  const source = readSource('src/views/tasks/Detail.vue')

  assert.equal(source.includes('TaskOutputSummary'), true)
  assert.equal(source.includes('TaskLogPreview'), true)
  assert.equal(source.includes('ResultVisualizationPanel'), true)
})

test('工作台轻量结果面板应复用结果可视化、输出摘要与日志预览', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/workflow/WorkflowTaskResultPanel.vue')), true)

  const source = readSource('src/components/workflow/WorkflowTaskResultPanel.vue')

  assert.equal(source.includes('ResultVisualizationPanel'), true)
  assert.equal(source.includes('TaskOutputSummary'), true)
  assert.equal(source.includes('TaskLogPreview'), true)
  assert.equal(source.includes('getTaskDetail'), true)
  assert.equal(source.includes('getTaskLogs'), true)
  assert.equal(source.includes('workflow.currentTool.viewTask'), true)
})

test('工作台页应提供节点结果标签、任务详情与产物下载入口', () => {
  const source = readSource('src/views/workflow/index.vue')
  const inspectorSource = readSource('src/components/workflow/WorkflowNodeInspector.vue')

  assert.equal(source.includes('WorkflowResultsReportPanel'), true)
  assert.equal(inspectorSource.includes("workflow.inspector.taskResult"), true)
  assert.equal(inspectorSource.includes("event: 'view-task-detail'"), true)
  assert.equal(inspectorSource.includes('handleDownloadOutput'), true)
})
