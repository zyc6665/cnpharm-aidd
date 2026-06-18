import type { WorkflowStepStatus } from './artifact-types.ts'
import type { WorkflowTemplate } from './template-types.ts'

export type WorkflowPreflightIssueType =
  | 'missing_tool'
  | 'waiting_input'
  | 'running'
  | 'failed'
  | 'invalidated'

export type WorkflowPreflightSeverity = 'error' | 'warning' | 'info'

export interface WorkflowPreflightIssue {
  id: string
  nodeId: string
  nodeTitle: string
  type: WorkflowPreflightIssueType
  severity: WorkflowPreflightSeverity
  title: string
  detail: string
}

export interface WorkflowPreflightSummary {
  canRun: boolean
  runnableCount: number
  blockedCount: number
  completedCount: number
  runningCount: number
  failedCount: number
  issues: WorkflowPreflightIssue[]
  primaryMessage: string
}

export function buildWorkflowPreflight(input: {
  template: WorkflowTemplate
  nodeStatuses: Record<string, WorkflowStepStatus>
  readyNodeIds: string[]
}): WorkflowPreflightSummary {
  const toolNodes = input.template.nodes.filter(node => node.type === 'tool')
  const readyNodeIds = new Set(input.readyNodeIds)
  const issues: WorkflowPreflightIssue[] = []
  let completedCount = 0
  let runningCount = 0
  let failedCount = 0

  for (const node of toolNodes) {
    const status = input.nodeStatuses[node.id] ?? 'idle'
    if (status === 'completed') {
      completedCount += 1
    }
    if (status === 'running') {
      runningCount += 1
      issues.push(createIssue(node.id, formatKey(node.titleKey), 'running'))
    }
    if (status === 'failed') {
      failedCount += 1
      issues.push(createIssue(node.id, formatKey(node.titleKey), 'failed'))
    }
    if (status === 'invalidated') {
      issues.push(createIssue(node.id, formatKey(node.titleKey), 'invalidated'))
    }
    if (status === 'needs_tool_selection') {
      issues.push(createIssue(node.id, formatKey(node.titleKey), 'missing_tool'))
    }
    if (status === 'idle' && node.requiredInputTypes?.length) {
      issues.push(createIssue(node.id, formatKey(node.titleKey), 'waiting_input'))
    }
  }

  const runnableCount = toolNodes.filter(node => readyNodeIds.has(node.id)).length
  const blockedCount = issues.filter(issue => issue.type === 'missing_tool' || issue.type === 'waiting_input').length

  return {
    canRun: runnableCount > 0 && runningCount === 0,
    runnableCount,
    blockedCount,
    completedCount,
    runningCount,
    failedCount,
    issues,
    primaryMessage: runnableCount > 0 ? `有 ${runnableCount} 个节点可运行` : '当前没有可运行节点'
  }
}

function createIssue(
  nodeId: string,
  nodeTitle: string,
  type: WorkflowPreflightIssueType
): WorkflowPreflightIssue {
  const issueTextByType: Record<WorkflowPreflightIssueType, {
    severity: WorkflowPreflightSeverity
    title: string
    detail: string
  }> = {
    missing_tool: {
      severity: 'error',
      title: '缺少工具选择',
      detail: '该节点有多个候选工具，运行前需要先指定工具。'
    },
    waiting_input: {
      severity: 'warning',
      title: '等待上游输入',
      detail: '该节点需要上游产物，当前还没有满足要求的成功任务结果。'
    },
    running: {
      severity: 'info',
      title: '节点正在运行',
      detail: '等待当前任务结束后再继续运行后续节点。'
    },
    failed: {
      severity: 'error',
      title: '节点任务失败',
      detail: '请检查任务日志或调整参数后重新运行该节点。'
    },
    invalidated: {
      severity: 'warning',
      title: '节点需要重跑',
      detail: '上游输入或参数已经变化，建议重新运行该节点。'
    }
  }
  const text = issueTextByType[type]

  return {
    id: `${nodeId}-${type}`,
    nodeId,
    nodeTitle,
    type,
    severity: text.severity,
    title: text.title,
    detail: text.detail
  }
}

function formatKey(key: string): string {
  const segments = key.split('.')
  const lastSegment = segments[segments.length - 1] ?? key
  return lastSegment
    .replace(/([A-Z])/g, ' $1')
    .replace(/[-_]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}
