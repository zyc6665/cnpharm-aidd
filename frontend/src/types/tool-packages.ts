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

export interface KubernetesRegistrationVariant {
  name: string
  accelerator: string
  entrypoint: string[]
  resources: Record<string, unknown>
}

export interface KubernetesToolVersionSummary {
  id: string
  version: string
  executor_type: string | null
  is_active: boolean
  deprecated: boolean
  smoke_status: string | null
  smoke_task_id: string | null
  smoke_created_at: string | null
}

export interface KubernetesToolVersionSmokeInput {
  name?: string
  project_id?: string
  params?: Record<string, unknown>
  file_ids?: string[]
  input_bindings?: Record<string, string>
  standard_input_uploads?: Record<string, string>
}

export interface KubernetesToolVersionSmokeResult {
  task_id: string
  tool_id: string
  tool_version_id: string
  status: string
  run_kind: 'tool_version_smoke'
}

export interface KubernetesToolVersionPromotionResult {
  tool_id: string
  tool_version_id: string
  current_version_id: string
  is_active: boolean
}

export interface KubernetesRegistrationOptions {
  package_id: string
  package_version_id: string
  package_version: string
  manifest_digest: string
  kubernetes_supported: boolean
  image: string | null
  image_digest: string | null
  variants: KubernetesRegistrationVariant[]
  resource_profiles: string[]
  tool_versions: KubernetesToolVersionSummary[]
  existing_tool: {
    id: string
    name: string
    slug: string
    status: string
    current_version_id: string | null
    current_version_type: string | null
  } | null
}

export interface KubernetesToolRegistrationInput {
  package_version_id: string
  target_tool_id?: string | null
  category_id?: string | null
  tool_version: string
  variant_name: string
  resource_profile: string
}

export interface KubernetesToolRegistrationResult {
  registration_status: 'candidate'
  tool: {
    id: string
    slug: string
    name: string
    status: string
    current_version_id: string | null
  }
  version: {
    id: string
    tool_id: string
    version: string
    is_active: boolean
    deprecated: boolean
    config: Record<string, unknown>
  }
}
