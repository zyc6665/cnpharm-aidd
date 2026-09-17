import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { buildWorkflowReportMarkdown } from '../src/workflow/report.ts'

test('workflow results report panel exposes summary and export surface', () => {
  const componentPath = resolve('src/components/workflow/WorkflowResultsReportPanel.vue')

  assert.equal(existsSync(componentPath), true)
  const source = readFileSync(componentPath, 'utf8')

  for (const marker of [
    'workflow-results-report-panel',
    'buildWorkflowReportMarkdown',
    'exportWorkflowReportMarkdown',
    'useI18n',
    'workflow.resultsReport.export',
    'workflow.resultsReport.nodeResults',
    'workflow.resultsReport.artifactSummary',
    'workflow.resultsReport.decisionSummary'
  ]) {
    assert.equal(source.includes(marker), true, `missing ${marker}`)
  }

  for (const literal of [
    '结果中心',
    '未命名工作流',
    '决策摘要',
    '导出报告',
    '节点结果',
    '成功节点',
    '失败节点',
    '产物摘要',
    '无产物',
    '存在失败节点，建议先检查失败原因和输入产物。',
    '已有可复核产物，可进入下一步筛选或团队评审。',
    '暂无可用于决策的完整结果。'
  ]) {
    assert.equal(source.includes(literal), false, `hardcoded report panel literal: ${literal}`)
  }
})

test('workflow markdown report should use injected labels', async () => {
  const markdown = buildWorkflowReportMarkdown({
    workflowName: '',
    decisionSummary: 'Review failed nodes first.',
    rows: [
      {
        nodeId: 'dock',
        nodeTitle: 'Docking',
        status: 'failed',
        statusLabel: 'Failed',
        taskId: undefined,
        artifacts: []
      },
      {
        nodeId: 'score',
        nodeTitle: 'Scoring',
        status: 'completed',
        statusLabel: 'Completed',
        taskId: 'task-1',
        artifacts: [
          { id: 'a1', filename: 'score.csv', url: '/files/a1' },
          { id: 'a2', filename: 'pose.sdf', url: '/files/a2' }
        ]
      }
    ],
    labels: {
      workflowNameFallback: 'Untitled Workflow',
      reportTitleSuffix: 'Report',
      decisionSummaryTitle: 'Decision Summary',
      nodeResultsTitle: 'Node Results',
      artifactSummaryTitle: 'Artifact Summary',
      tableNode: 'Node',
      tableStatus: 'Status',
      tableTask: 'Task',
      tableArtifacts: 'Artifacts',
      noArtifacts: 'No artifacts',
      artifactSummaryLine: (count: number) => `${count} artifacts total.`
    }
  })

  assert.equal(markdown.includes('# Untitled Workflow Report'), true)
  assert.equal(markdown.includes('| Node | Status | Task | Artifacts |'), true)
  assert.equal(markdown.includes('No artifacts'), true)
  assert.equal(markdown.includes('2 artifacts total.'), true)

  for (const literal of ['未命名工作流', '决策摘要', '节点结果', '无产物', '产物摘要']) {
    assert.equal(markdown.includes(literal), false, `hardcoded markdown literal: ${literal}`)
  }
})
