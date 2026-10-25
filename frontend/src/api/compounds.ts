import { del, get, post, put, type RequestOptions } from './request'
import type { ApiResponse } from '@/types/api'
import type { PaginatedResponse } from '@/types/models'
import type {
  Candidate,
  CandidateCompareResult,
  CandidateCreateInput,
  CandidateListParams,
  CandidateSet,
  CandidateSetCreateInput,
  CandidateSetExportResult,
  CandidateSetItem,
  CandidateSetItemsAddInput,
  CandidateSetItemsAddResult,
  CandidateSetListParams,
  CandidateSetUpdateInput,
  CandidateUpdateInput,
  Compound,
  CompoundCreateInput,
  CompoundImportInput,
  CompoundImportResult,
  CompoundListParams,
  CompoundSearchResult
} from '@/types/compounds'

/** compounds/results 相关请求统一静默失败（页面自己渲染错态）+ 一次重试。 */
const OPTIONS: RequestOptions = { silent: true, retry: 1 }

export const listCompounds = (
  projectId: string,
  params?: CompoundListParams
): Promise<ApiResponse<PaginatedResponse<Compound>>> => {
  return get<PaginatedResponse<Compound>, CompoundListParams>(
    `/projects/${projectId}/compounds`,
    params,
    OPTIONS
  )
}

export const createCompound = (
  projectId: string,
  input: CompoundCreateInput
): Promise<ApiResponse<Compound>> => {
  return post<Compound>(`/projects/${projectId}/compounds`, input, OPTIONS)
}

export const importCompounds = (
  projectId: string,
  input: CompoundImportInput
): Promise<ApiResponse<CompoundImportResult>> => {
  return post<CompoundImportResult>(`/projects/${projectId}/compounds:import`, input, OPTIONS)
}

export const getCompound = (compoundId: string): Promise<ApiResponse<Compound>> => {
  return get<Compound>(`/compounds/${compoundId}`, undefined, OPTIONS)
}

export const searchCompounds = (
  input: CompoundCreateInput,
  params?: { limit?: number; threshold?: number }
): Promise<ApiResponse<CompoundSearchResult>> => {
  return post<CompoundSearchResult>('/compounds:search', input, { ...OPTIONS, params })
}

export const listCandidates = (
  projectId: string,
  params?: CandidateListParams
): Promise<ApiResponse<PaginatedResponse<Candidate>>> => {
  return get<PaginatedResponse<Candidate>, CandidateListParams>(
    `/projects/${projectId}/candidates`,
    params,
    OPTIONS
  )
}

export const createCandidate = (
  projectId: string,
  input: CandidateCreateInput
): Promise<ApiResponse<Candidate>> => {
  return post<Candidate>(`/projects/${projectId}/candidates`, input, OPTIONS)
}

export const getCandidate = (candidateId: string): Promise<ApiResponse<Candidate>> => {
  return get<Candidate>(`/candidates/${candidateId}`, undefined, OPTIONS)
}

export const updateCandidate = (
  candidateId: string,
  input: CandidateUpdateInput
): Promise<ApiResponse<Candidate>> => {
  return put<Candidate>(`/candidates/${candidateId}`, input, OPTIONS)
}

export const compareCandidates = (
  projectId: string,
  candidateIds: string[]
): Promise<ApiResponse<CandidateCompareResult>> => {
  return post<CandidateCompareResult>(
    '/candidates:compare',
    { candidate_ids: candidateIds },
    { ...OPTIONS, params: { project_id: projectId } }
  )
}

export const listCandidateSets = (
  projectId: string,
  params?: CandidateSetListParams
): Promise<ApiResponse<PaginatedResponse<CandidateSet>>> => {
  return get<PaginatedResponse<CandidateSet>, CandidateSetListParams>(
    `/projects/${projectId}/candidate-sets`,
    params,
    OPTIONS
  )
}

export const createCandidateSet = (
  projectId: string,
  input: CandidateSetCreateInput
): Promise<ApiResponse<CandidateSet>> => {
  return post<CandidateSet>(`/projects/${projectId}/candidate-sets`, input, OPTIONS)
}

export const getCandidateSet = (setId: string): Promise<ApiResponse<CandidateSet>> => {
  return get<CandidateSet>(`/candidate-sets/${setId}`, undefined, OPTIONS)
}

export const updateCandidateSet = (
  setId: string,
  input: CandidateSetUpdateInput
): Promise<ApiResponse<CandidateSet>> => {
  return put<CandidateSet>(`/candidate-sets/${setId}`, input, OPTIONS)
}

export const listCandidateSetItems = (
  setId: string,
  params?: { page?: number; page_size?: number }
): Promise<ApiResponse<PaginatedResponse<CandidateSetItem>>> => {
  return get<PaginatedResponse<CandidateSetItem>, { page?: number; page_size?: number }>(
    `/candidate-sets/${setId}/items`,
    params,
    OPTIONS
  )
}

export const addCandidateSetItems = (
  setId: string,
  input: CandidateSetItemsAddInput
): Promise<ApiResponse<CandidateSetItemsAddResult>> => {
  return post<CandidateSetItemsAddResult>(`/candidate-sets/${setId}/items`, input, OPTIONS)
}

export const removeCandidateSetItem = (
  setId: string,
  itemId: string
): Promise<ApiResponse<{ candidate_set: CandidateSet }>> => {
  return del<{ candidate_set: CandidateSet }>(`/candidate-sets/${setId}/items/${itemId}`, OPTIONS)
}

export const exportCandidateSet = (
  setId: string
): Promise<ApiResponse<CandidateSetExportResult>> => {
  return post<CandidateSetExportResult>(`/candidate-sets/${setId}:export`, undefined, OPTIONS)
}
