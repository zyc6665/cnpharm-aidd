import { del, get, LONG_RUNNING_TIMEOUT_MS, post, type RequestOptions } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  AiddAgentRun,
  AiddAgentRunCreateParams,
  AiddWorkflowDraft,
  PaginatedResponse,
  PaginationParams
} from '@/types/models'

export interface AiddAgentRunListParams extends PaginationParams {
  project_only?: boolean
}

export const createAiddAgentRun = (
  data: AiddAgentRunCreateParams,
  options?: RequestOptions
): Promise<ApiResponse<AiddAgentRun>> => {
  return post<AiddAgentRun>('/agents/aidd/runs', data, {
    ...options,
    timeout: options?.timeout ?? LONG_RUNNING_TIMEOUT_MS
  })
}

export const createAiddWorkflowDraft = (
  data: AiddAgentRunCreateParams,
  options?: RequestOptions
): Promise<ApiResponse<AiddWorkflowDraft>> => {
  return post<AiddWorkflowDraft>('/agents/aidd/workflow-drafts', data, {
    ...options,
    timeout: options?.timeout ?? LONG_RUNNING_TIMEOUT_MS
  })
}

export const getAiddAgentRuns = (
  params?: AiddAgentRunListParams,
  options?: RequestOptions
): Promise<ApiResponse<PaginatedResponse<AiddAgentRun>>> => {
  return get<PaginatedResponse<AiddAgentRun>, AiddAgentRunListParams>(
    '/agents/aidd/runs',
    params,
    options
  )
}

export const getAiddAgentRun = (
  runId: string,
  options?: RequestOptions
): Promise<ApiResponse<AiddAgentRun>> => {
  return get<AiddAgentRun>(`/agents/aidd/runs/${runId}`, undefined, options)
}

export const cancelAiddAgentRun = (runId: string): Promise<ApiResponse<AiddAgentRun>> => {
  return post<AiddAgentRun>(`/agents/aidd/runs/${runId}/cancel`)
}

export const deleteAiddAgentRun = (
  runId: string,
  cascade = false
): Promise<ApiResponse<{ id: string; deleted_tasks: number; deleted_artifacts: number }>> => {
  return del<{ id: string; deleted_tasks: number; deleted_artifacts: number }>(
    `/agents/aidd/runs/${runId}`,
    { params: { cascade } }
  )
}

export const syncAiddAgentRun = (
  runId: string,
  options?: RequestOptions
): Promise<ApiResponse<AiddAgentRun>> => {
  return post<AiddAgentRun>(`/agents/aidd/runs/${runId}/sync`, undefined, {
    ...options,
    timeout: options?.timeout ?? LONG_RUNNING_TIMEOUT_MS
  })
}
