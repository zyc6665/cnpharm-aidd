import type { WorkflowDefinitionListParams, WorkflowRunListParams } from '@/api/workflows'

export interface WorkflowRouteProjectInput {
  paramsProjectId?: unknown
  queryProjectId?: unknown
}

export interface WorkflowRunListScope {
  projectId?: string
  workflowDefinitionId?: string
  /** 首屏 offset 用；cursor 模式下省略 */
  page?: number
  pageSize: number
  /** 加载更多时传入；一旦传入走 cursor 模式（不带 page） */
  cursor?: string
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
    ...(scope.cursor ? { cursor: scope.cursor } : { page: scope.page ?? 1 }),
    page_size: scope.pageSize,
    ...(scope.projectId ? { project_id: scope.projectId } : {}),
    ...(scope.workflowDefinitionId ? { workflow_definition_id: scope.workflowDefinitionId } : {})
  }
}
