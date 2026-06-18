import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

test('workflow results report panel exposes summary and export surface', () => {
  const componentPath = resolve('src/components/workflow/WorkflowResultsReportPanel.vue')

  assert.equal(existsSync(componentPath), true)
  const source = readFileSync(componentPath, 'utf8')

  for (const marker of [
    'workflow-results-report-panel',
    'buildWorkflowReportMarkdown',
    'exportWorkflowReportMarkdown',
    '导出报告',
    '节点结果',
    '产物摘要',
    '决策摘要'
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }
})
