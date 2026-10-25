import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工作台不再使用旧运行面板承载轻量结果', () => {
  const resultPanelSource = readSource('src/components/workflow/NodeResultPanel.vue')
  const pageSource = readSource('src/views/workflow/index.vue')

  assert.equal(existsSync(resolve(rootDir, 'src/components/workflow/WorkflowRunPanel.vue')), false)
  assert.equal(resultPanelSource.includes('view-task-detail'), true)
  assert.equal(pageSource.includes('WorkflowResultsReportPanel'), true)
})

test('任务详情页应复用共享输出摘要和日志预览组件', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/TaskOutputSummary.vue')), true)
  assert.equal(existsSync(resolve(rootDir, 'src/components/tasks/TaskLogPreview.vue')), true)

  const source = readSource('src/views/tasks/Detail.vue')

  assert.equal(source.includes('TaskOutputSummary'), true)
  assert.equal(source.includes('TaskLogPreview'), true)
  assert.equal(source.includes('ResultVisualizationPanel'), true)
})

test('工作台不应保留未引用的任务结果面板，且 results 命名空间必须存在并被消费', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/workflow/WorkflowTaskResultPanel.vue')), false)

  // P-33/P-34 结果中心上线后，results 命名空间由 src/views/results/ 消费，
  // 不再属于「孤儿翻译」；此处守住「命名空间必须有用例引用」这一原始意图。
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')
  const resultListView = readSource('src/views/results/List.vue')
  const resultDetailView = readSource('src/views/results/ResultDetail.vue')

  // 两份 locale 都必须真的声明了 results 命名空间（拆成两条硬断言，避免联合断言同时为假时逃逸）
  assert.equal(zhSource.includes('results: {'), true)
  assert.equal(enSource.includes('results: {'), true)
  assert.equal(resultListView.includes("results."), true)
  assert.equal(resultDetailView.includes("results."), true)
})

test('工作台页应提供节点结果标签、任务详情与产物下载入口', () => {
  const source = readSource('src/views/workflow/index.vue')
  const inspectorSource = readSource('src/components/workflow/WorkflowNodeInspector.vue')
  const resultPanelSource = readSource('src/components/workflow/NodeResultPanel.vue')

  assert.equal(source.includes('WorkflowResultsReportPanel'), true)
  assert.equal(inspectorSource.includes('NodeResultPanel'), true)
  assert.equal(inspectorSource.includes("event: 'view-task-detail'"), true)
  assert.equal(resultPanelSource.includes("workflow.inspector.taskResult"), true)
  assert.equal(resultPanelSource.includes('triggerProtectedFileDownload'), true)
})
