import { LONG_RUNNING_TIMEOUT_MS, get, post } from './request'
import type { ApiResponse } from '@/types/api'
import type { TypedArtifact } from '@/types/artifacts'

export type ExternalDatabaseEntityType = 'ligand' | 'protein'

export interface ExternalDatabaseSource {
  id: string
  name: string
  entity_types: ExternalDatabaseEntityType[]
  identifier_label: string
}

export interface ExternalDatabaseSourcesResponse {
  sources: ExternalDatabaseSource[]
}

export interface ExternalDatabaseImportPayload {
  source: string
  entity_type: ExternalDatabaseEntityType
  identifier: string
}

export interface ExternalDatabaseImportResult {
  artifact: TypedArtifact
}

export const getExternalDatabaseSources = (): Promise<
  ApiResponse<ExternalDatabaseSourcesResponse>
> => get<ExternalDatabaseSourcesResponse>('/external-databases/sources')

export const importExternalDatabaseArtifact = (
  projectId: string,
  payload: ExternalDatabaseImportPayload
): Promise<ApiResponse<ExternalDatabaseImportResult>> => {
  return post<ExternalDatabaseImportResult>(
    `/projects/${projectId}/external-databases/import`,
    payload,
    { timeout: LONG_RUNNING_TIMEOUT_MS }
  )
}
