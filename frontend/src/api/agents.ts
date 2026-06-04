import { del, get, post } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  AiddAgentRun,
  AiddAgentRunCreateParams,
  PaginatedResponse,
  PaginationParams
} from '@/types/models'

export const createAiddAgentRun = (data: AiddAgentRunCreateParams): Promise<ApiResponse<AiddAgentRun>> => {
  return post<AiddAgentRun>('/agents/aidd/runs', data)
}

export const getAiddAgentRuns = (
  params?: PaginationParams
): Promise<ApiResponse<PaginatedResponse<AiddAgentRun>>> => {
  return get<PaginatedResponse<AiddAgentRun>>('/agents/aidd/runs', params as Record<string, unknown>)
}

export const getAiddAgentRun = (runId: string): Promise<ApiResponse<AiddAgentRun>> => {
  return get<AiddAgentRun>(`/agents/aidd/runs/${runId}`)
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

export const syncAiddAgentRun = (runId: string): Promise<ApiResponse<AiddAgentRun>> => {
  return post<AiddAgentRun>(`/agents/aidd/runs/${runId}/sync`)
}
