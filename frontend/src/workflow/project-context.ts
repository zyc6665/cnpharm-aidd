import type { WorkflowDefinitionListParams, WorkflowRunListParams } from '@/api/workflows'

export interface WorkflowRouteProjectInput {
  paramsProjectId?: unknown
  queryProjectId?: unknown
}

export interface WorkflowRunListScope {
  projectId?: string
  workflowDefinitionId?: string
  page: number
  pageSize: number
}

function normalizeProjectId(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined
  }

  const trimmed = value.trim()
  return trimmed || undefined
}

export function resolveWorkflowRouteProjectId(input: WorkflowRouteProjectInput): string | undefined {
  return normalizeProjectId(input.paramsProjectId) ?? normalizeProjectId(input.queryProjectId)
}

export function buildWorkflowDefinitionListParams(
  projectId: string | undefined
): WorkflowDefinitionListParams {
  return {
    page: 1,
    page_size: 100,
    ...(projectId ? { project_id: projectId } : {})
  }
}

export function buildWorkflowRunListParams(scope: WorkflowRunListScope): WorkflowRunListParams {
  return {
    page: scope.page,
    page_size: scope.pageSize,
    ...(scope.projectId ? { project_id: scope.projectId } : {}),
    ...(scope.workflowDefinitionId ? { workflow_definition_id: scope.workflowDefinitionId } : {})
  }
}
