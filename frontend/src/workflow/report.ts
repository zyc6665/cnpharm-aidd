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

export interface WorkflowReportMarkdownLabels {
  workflowNameFallback: string
  reportTitleSuffix: string
  decisionSummaryTitle: string
  nodeResultsTitle: string
  artifactSummaryTitle: string
  tableNode: string
  tableStatus: string
  tableTask: string
  tableArtifacts: string
  noArtifacts: string
  artifactSummaryLine: (artifactCount: number) => string
}

const DEFAULT_WORKFLOW_REPORT_LABELS: WorkflowReportMarkdownLabels = {
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
  artifactSummaryLine: (artifactCount) => `${artifactCount} artifacts total.`
}

export function buildWorkflowReportMarkdown(input: {
  workflowName: string
  rows: WorkflowReportRow[]
  decisionSummary: string
  labels?: WorkflowReportMarkdownLabels
}): string {
  const labels = input.labels ?? DEFAULT_WORKFLOW_REPORT_LABELS
  const artifactCount = input.rows.reduce((count, row) => count + row.artifacts.length, 0)
  const workflowName = input.workflowName || labels.workflowNameFallback
  const lines = [
    `# ${workflowName} ${labels.reportTitleSuffix}`,
    '',
    `## ${labels.decisionSummaryTitle}`,
    '',
    input.decisionSummary,
    '',
    `## ${labels.nodeResultsTitle}`,
    '',
    `| ${labels.tableNode} | ${labels.tableStatus} | ${labels.tableTask} | ${labels.tableArtifacts} |`,
    '| --- | --- | --- | --- |'
  ]

  for (const row of input.rows) {
    const artifactLinks = row.artifacts.length
      ? row.artifacts.map(artifact => `[${artifact.filename}](${artifact.url})`).join('<br>')
      : labels.noArtifacts
    lines.push(`| ${row.nodeTitle} | ${row.statusLabel || row.status} | ${row.taskId ?? '-'} | ${artifactLinks} |`)
  }

  lines.push('', `## ${labels.artifactSummaryTitle}`, '', labels.artifactSummaryLine(artifactCount))
  return `${lines.join('\n')}\n`
}
