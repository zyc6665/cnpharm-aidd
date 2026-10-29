import { get, post } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  ArtifactLineageGraph,
  ArtifactListResponse,
  ArtifactUploadInput,
  TypedArtifact
} from '@/types/artifacts'

export interface ProjectArtifactListParams {
  artifact_type?: string
  semantic_type?: string
  standard_type?: string
  source_task_id?: string
  file_role?: string
  metadata_model_name?: string
  metadata_model_version?: string
  metadata_evidence_level?: string
  metadata_endpoint_ref?: string
  metadata_applicability_domain_status?: string
  page?: number
  page_size?: number
}

export const getProjectArtifacts = (
  projectId: string,
  params?: ProjectArtifactListParams
): Promise<ApiResponse<ArtifactListResponse>> => {
  // 分页接口：参数原样透传，不塞默认 page_size，避免调用方误以为拿到了全量。
  return get<ArtifactListResponse, ProjectArtifactListParams>(
    `/projects/${projectId}/artifacts`,
    params
  )
}

const ARTIFACT_PAGE_SIZE = 100

/**
 * 取全量产物：按 page_size=100 逐页拉取并合并 items。
 *
 * 后端列表接口已分页，单次最多 100 条；需要「全量」的页面必须走这里，
 * 否则超过 100 条的产物会被静默截断。
 */
export const getAllProjectArtifacts = async (
  projectId: string,
  params?: Omit<ProjectArtifactListParams, 'page' | 'page_size'>
): Promise<ApiResponse<ArtifactListResponse>> => {
  const items: TypedArtifact[] = []
  let page = 1
  let total = 0
  let lastResponse!: ApiResponse<ArtifactListResponse>

  do {
    const response = await getProjectArtifacts(projectId, {
      ...params,
      page,
      page_size: ARTIFACT_PAGE_SIZE,
    })
    lastResponse = response
    items.push(...response.data.items)
    total = response.data.total ?? 0
    page += 1
  } while ((page - 1) * ARTIFACT_PAGE_SIZE < total)

  return {
    ...lastResponse,
    data: {
      ...lastResponse.data,
      items,
      total,
    },
  }
}

export const getArtifact = (artifactId: string): Promise<ApiResponse<TypedArtifact>> => {
  return get<TypedArtifact>(`/artifacts/${artifactId}`)
}

export const getProjectArtifactLineage = (
  projectId: string
): Promise<ApiResponse<ArtifactLineageGraph>> => {
  return get<ArtifactLineageGraph>(`/projects/${projectId}/artifact-lineage`)
}

export const uploadProjectArtifact = (
  projectId: string,
  input: ArtifactUploadInput
): Promise<ApiResponse<TypedArtifact>> => {
  const formData = new FormData()
  formData.append('file', input.file)
  formData.append('artifact_type', input.artifact_type)
  formData.append('semantic_type', input.semantic_type)
  if (input.standard_type) {
    formData.append('standard_type', input.standard_type)
  }
  if (input.standard_version !== undefined) {
    formData.append('standard_version', String(input.standard_version))
  }

  if (input.description) {
    formData.append('description', input.description)
  }

  if (input.expires_at) {
    formData.append('expires_at', input.expires_at)
  }

  return post<TypedArtifact>(`/projects/${projectId}/artifacts`, formData, {
    timeout: 5 * 60_000,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const uploadArtifactVersion = (
  artifactId: string,
  file: File,
  options?: { expires_at?: string }
): Promise<ApiResponse<TypedArtifact>> => {
  const formData = new FormData()
  formData.append('file', file)

  if (options?.expires_at) {
    formData.append('expires_at', options.expires_at)
  }

  return post<TypedArtifact>(`/artifacts/${artifactId}/versions`, formData, {
    timeout: 5 * 60_000,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const buildArtifactVersionDownloadUrl = (
  artifactId: string,
  versionId: string
): string => {
  return `/api/v1/artifacts/${artifactId}/versions/${versionId}/download`
}
