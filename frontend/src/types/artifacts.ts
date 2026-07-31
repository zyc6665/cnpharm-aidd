export type ArtifactType = 'protein_structure' | 'pocket_result' | 'file' | 'run_report'

export interface ArtifactVersion {
  id: string
  version: number
  filename: string
  content_type?: string | null
  size_bytes: number
  sha256: string
  status: string
  expires_at?: string | null
  created_at: string
}

export interface TypedArtifact {
  id: string
  project_id: string
  artifact_type: ArtifactType | (string & {})
  semantic_type: string
  name: string
  description?: string | null
  latest_version: ArtifactVersion
  versions?: ArtifactVersion[]
  deduplicated?: boolean
  created_at: string
  updated_at: string
  [key: string]: unknown
}

export interface ArtifactListResponse {
  items: TypedArtifact[]
}

export interface ArtifactUploadInput {
  file: File
  artifact_type: ArtifactType | string
  semantic_type: string
  description?: string
  expires_at?: string
}
