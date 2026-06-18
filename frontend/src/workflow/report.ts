export interface WorkflowReportArtifactLink {
  id: string
  filename: string
  url: string
}

export interface WorkflowReportRow {
  nodeId: string
  nodeTitle: string
  status: string
  statusLabel: string
  taskId?: string
  taskStatus?: string
  artifacts: WorkflowReportArtifactLink[]
}

export function buildWorkflowReportMarkdown(input: {
  workflowName: string
  rows: WorkflowReportRow[]
  decisionSummary: string
}): string {
  const artifactCount = input.rows.reduce((count, row) => count + row.artifacts.length, 0)
  const lines = [
    `# ${input.workflowName || '未命名工作流'} 报告`,
    '',
    '## 决策摘要',
    '',
    input.decisionSummary,
    '',
    '## 节点结果',
    '',
    '| 节点 | 状态 | 任务 | 产物 |',
    '| --- | --- | --- | --- |'
  ]

  for (const row of input.rows) {
    const artifactLinks = row.artifacts.length
      ? row.artifacts.map(artifact => `[${artifact.filename}](${artifact.url})`).join('<br>')
      : '无产物'
    lines.push(`| ${row.nodeTitle} | ${row.statusLabel || row.status} | ${row.taskId ?? '-'} | ${artifactLinks} |`)
  }

  lines.push('', '## 产物摘要', '', `共 ${artifactCount} 个产物。`)
  return `${lines.join('\n')}\n`
}
