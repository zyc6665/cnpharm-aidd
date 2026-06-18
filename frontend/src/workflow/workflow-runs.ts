import type { WorkflowRun } from '../types/models'

export type WorkflowRunTone = 'default' | 'processing' | 'success' | 'error' | 'warning'

export interface WorkflowRunNodeSummary {
  id: string
  status: string
  toolSlug: string | null
  taskId: string | null
  errorMessage: string | null
}

export interface WorkflowRunSummary {
  total: number
  completed: number
  running: number
  failed: number
  pending: number
  percent: number
  nodes: WorkflowRunNodeSummary[]
}

export interface WorkflowRunAutoSyncState {
  isLoggedIn: boolean
  isLoading: boolean
  isSyncing: boolean
}

function readNodeStateValue(state: unknown, key: string): unknown {
  if (!state || typeof state !== 'object') {
    return null
  }

  return (state as Record<string, unknown>)[key]
}

function normalizeStatus(value: unknown): string {
  return typeof value === 'string' && value ? value : 'pending'
}

function normalizeOptionalString(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

export function isWorkflowRunTerminal(status: string): boolean {
  return ['success', 'failure', 'canceled'].includes(status)
}

export function getWorkflowRunStatusTone(status: string): WorkflowRunTone {
  if (status === 'success') {
    return 'success'
  }
  if (status === 'failure') {
    return 'error'
  }
  if (status === 'canceled') {
    return 'warning'
  }
  if (['running', 'waiting_task', 'pending'].includes(status)) {
    return 'processing'
  }
  return 'default'
}

export function shouldAutoSyncWorkflowRun(
  run: WorkflowRun | null,
  state: WorkflowRunAutoSyncState
): boolean {
  if (!run || !state.isLoggedIn || state.isLoading || state.isSyncing) {
    return false
  }

  return !isWorkflowRunTerminal(run.status)
}

export function buildWorkflowRunSummary(run: WorkflowRun | null): WorkflowRunSummary {
  if (!run) {
    return {
      total: 0,
      completed: 0,
      running: 0,
      failed: 0,
      pending: 0,
      percent: 0,
      nodes: []
    }
  }

  const nodeIds = run.execution_order?.length
    ? run.execution_order
    : Object.keys(run.node_states ?? {})

  const nodes = nodeIds.map((nodeId) => {
    const state = (run.node_states ?? {})[nodeId]
    return {
      id: nodeId,
      status: normalizeStatus(readNodeStateValue(state, 'status')),
      toolSlug: normalizeOptionalString(readNodeStateValue(state, 'tool_slug')),
      taskId: normalizeOptionalString(readNodeStateValue(state, 'task_id')),
      errorMessage: normalizeOptionalString(readNodeStateValue(state, 'error_message'))
    }
  })

  const completed = nodes.filter((node) => node.status === 'success').length
  const failed = nodes.filter((node) => node.status === 'failure').length
  const running = nodes.filter((node) =>
    ['running', 'waiting_task', 'ready'].includes(node.status)
  ).length
  const pending = Math.max(nodes.length - completed - failed - running, 0)

  return {
    total: nodes.length,
    completed,
    running,
    failed,
    pending,
    percent: nodes.length > 0 ? Math.round((completed / nodes.length) * 100) : 0,
    nodes
  }
}
