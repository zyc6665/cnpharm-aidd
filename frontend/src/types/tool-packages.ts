export interface ToolPackageVersion {
  id: string
  version: string
  manifest: Record<string, unknown>
  manifest_digest: string
  signature?: string | null
  is_signed: boolean
  validation_status: string
  validation_errors: string[]
}

export interface ToolPackage {
  id: string
  slug: string
  name: string
  description?: string | null
  status: 'draft' | 'published' | string
  owner_id: string
  current_version?: ToolPackageVersion | null
  created_at: string
  updated_at: string
}

export interface ToolPackageCreateInput {
  manifest: Record<string, unknown>
  signature?: string | null
}
