import { get, post, type RequestOptions } from './request'
import type { ApiResponse } from '@/types/api'
import type { PaginatedResponse } from '@/types/models'
import type {
  ProjectResultDetail,
  ProjectResultListParams,
  ProjectResultSummary,
  TraceabilityExportResult,
  TraceabilityPackage
} from '@/types/compounds'

/** results 相关请求统一静默失败（页面自己渲染错态）+ 一次重试。 */
const OPTIONS: RequestOptions = { silent: true, retry: 1 }

export const listProjectResults = (
  projectId: string,
  params?: ProjectResultListParams
): Promise<ApiResponse<PaginatedResponse<ProjectResultSummary>>> => {
  return get<PaginatedResponse<ProjectResultSummary>, ProjectResultListParams>(
    `/projects/${projectId}/results`,
    params,
    OPTIONS
  )
}

export const getResult = (taskId: string): Promise<ApiResponse<ProjectResultDetail>> => {
  return get<ProjectResultDetail>(`/results/${taskId}`, undefined, OPTIONS)
}

/**
 * 某个候选物相关的计算结果。
 *
 * 后端按两个方向取并集：**产出该候选物的任务**（`Candidate.task_id`）与**为它提交的
 * 任务**（提交时声明 `candidate_id`）。前者一定存在，所以这个列表不再是永远空的。
 */
export const listCandidateResults = (
  candidateId: string,
  params?: { page?: number; page_size?: number }
): Promise<ApiResponse<PaginatedResponse<ProjectResultSummary>>> => {
  return get<PaginatedResponse<ProjectResultSummary>, { page?: number; page_size?: number }>(
    `/candidates/${candidateId}/results`,
    params,
    OPTIONS
  )
}

export const getTraceability = (taskId: string): Promise<ApiResponse<TraceabilityPackage>> => {
  return get<TraceabilityPackage>(`/results/${taskId}/traceability`, undefined, OPTIONS)
}

export const exportTraceability = (
  taskId: string
): Promise<ApiResponse<TraceabilityExportResult>> => {
  return post<TraceabilityExportResult>(`/results/${taskId}:export`, undefined, OPTIONS)
}
