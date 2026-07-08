import type { WorkflowRun, WorkflowRunMissingOutput, WorkflowRunNodeState } from '../types/models'

export type WorkflowRunTone = 'default' | 'processing' | 'success' | 'error' | 'warning'

export interface WorkflowRunNodeSummary {
  id: string
  status: string
  toolSlug: string | null
  toolVersionId: string | null
  taskId: string | null
  inputFileIds: string[]
  outputSemanticTypes: string[]
  paramsText: string | null
  missingOutputs: WorkflowRunMissingOutput[]
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

type UnknownRecord = Record<string, unknown>

function isUnknownRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function asNodeState(state: WorkflowRunNodeState | unknown): UnknownRecord | null {
  return isUnknownRecord(state) ? state : null
}

function normalizeStatus(value: unknown): string {
  return typeof value === 'string' && value ? value : 'pending'
}

function normalizeOptionalString(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

function normalizeStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item.length > 0)
    : []
}

function normalizeSemanticOutputs(value: unknown): string[] {
  if (!isUnknownRecord(value)) {
    return []
  }

  return Object.keys(value)
}

function normalizeParamsText(value: unknown): string | null {
  if (!isUnknownRecord(value)) {
    return null
  }

  const entries = Object.entries(value)
  if (entries.length === 0) {
    return null
  }

  return entries.map(([key, entry]) => `${key}: ${JSON.stringify(entry)}`).join(', ')
}

function normalizeMissingOutputMatch(value: unknown): WorkflowRunMissingOutput['match'] {
  if (!isUnknownRecord(value)) {
    return { filename_contains_any: [] }
  }

  return {
    extension: normalizeOptionalString(value.extension),
    filename_contains_any: normalizeStringArray(value.filename_contains_any),
    content_type: normalizeOptionalString(value.content_type)
  }
}

function normalizeMissingOutputs(value: unknown): WorkflowRunMissingOutput[] {
  if (!Array.isArray(value)) {
    return []
  }

  return value.flatMap((item): WorkflowRunMissingOutput[] => {
    if (!isUnknownRecord(item)) {
      return []
    }

    const semanticType = normalizeOptionalString(item.semantic_type)
    const source = normalizeOptionalString(item.source)
    if (!semanticType || !source) {
      return []
    }

    return [
      {
        semantic_type: semanticType,
        source,
        path: normalizeOptionalString(item.path),
        required: item.required === true,
        match: normalizeMissingOutputMatch(item.match)
      }
    ]
  })
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
    const state = asNodeState((run.node_states ?? {})[nodeId])
    return {
      id: nodeId,
      status: normalizeStatus(state?.status),
      toolSlug: normalizeOptionalString(state?.tool_slug),
      toolVersionId: normalizeOptionalString(state?.tool_version_id),
      taskId: normalizeOptionalString(state?.task_id),
      inputFileIds: normalizeStringArray(state?.input_file_ids),
      outputSemanticTypes: normalizeSemanticOutputs(state?.semantic_outputs),
      paramsText: normalizeParamsText(state?.params),
      missingOutputs: normalizeMissingOutputs(state?.missing_outputs),
      errorMessage: normalizeOptionalString(state?.error_message)
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
