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
  metadata_model_version?: string
  metadata_evidence_level?: string
}

export const getProjectArtifacts = (
  projectId: string,
  params?: ProjectArtifactListParams
): Promise<ApiResponse<ArtifactListResponse>> => {
  return get<ArtifactListResponse, ProjectArtifactListParams>(`/projects/${projectId}/artifacts`, params)
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
