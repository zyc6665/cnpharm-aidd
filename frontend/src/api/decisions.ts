import { get, post, type RequestOptions } from './request'
import type { ApiResponse } from '@/types/api'
import type { PaginatedResponse } from '@/types/models'
import type {
  DecisionCreateParams,
  DecisionListParams,
  DecisionRecord,
  ProjectStage
} from '@/types/decisions'

/** 决策相关请求统一静默失败（页面自己渲染错态）+ 一次重试。 */
const OPTIONS: RequestOptions = { silent: true, retry: 1 }

/** `GET /projects/{id}/decisions` — 决策记录列表，按决策时间倒序分页。 */
export const listProjectDecisions = (
  projectId: string,
  params?: DecisionListParams
): Promise<ApiResponse<PaginatedResponse<DecisionRecord>>> => {
  return get<PaginatedResponse<DecisionRecord>, DecisionListParams>(
    `/projects/${projectId}/decisions`,
    params,
    OPTIONS
  )
}

/**
 * `POST /projects/{id}/decisions` — 提交一次研发决策。
 *
 * 决策记录只追加、不可修改不可删除（docs/10 DB-09），所以这里只有 POST，
 * 没有配套的 PUT / DELETE。
 */
export const createProjectDecision = (
  projectId: string,
  payload: DecisionCreateParams
): Promise<ApiResponse<DecisionRecord>> => {
  return post<DecisionRecord>(`/projects/${projectId}/decisions`, payload, OPTIONS)
}

/** `GET /projects/{id}/stage` — 当前研发阶段与缺口提示（只读推导，不落库）。 */
export const getProjectStage = (projectId: string): Promise<ApiResponse<ProjectStage>> => {
  return get<ProjectStage>(`/projects/${projectId}/stage`, undefined, OPTIONS)
}
