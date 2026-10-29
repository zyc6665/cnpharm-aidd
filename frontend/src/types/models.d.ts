import type { TypedArtifact } from './artifacts'

// 契约枚举统一 re-export 自 codegen 产物（计划 §3.2，勿手改）。
export type {
  ProjectStatus,
  ProjectRole,
  TaskPriority,
  AssetArtifactType,
  AuditAction,
  AuditResult,
  ResourceType,
} from './enums.generated'

// 用户相关类型
export interface UserInfo {
  id: string  // UUID
  email: string
  display_name?: string
  username?: string  // 用户名（兼容旧代码）
  avatar_url?: string
  avatar?: string  // 头像URL（兼容旧代码，实际使用avatar_url）
  role: 'user' | 'admin'
  status: 'active' | 'disabled' | 'pending'
  daily_task_limit?: number
  max_file_size_mb?: number
  statistics?: {
    total_tasks?: number
    successful_tasks?: number
    failed_tasks?: number
    total_tool_usage?: number
    last_active_at?: string | null
  }
  created_at: string
  updated_at: string
}

export interface AdminUserListResponse {
  total: number
  items: UserInfo[]
  page: number
  page_size: number
}

export interface AdminUserStats {
  total_users: number
  active_users: number
  admin_users: number
  new_users_today: number
  new_users_this_week: number
}

export interface LoginParams {
  email: string
  password: string
  remember?: boolean
}

export interface RegisterParams {
  email: string
  password: string
  verification_code: string
  display_name?: string
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface LoginResponse {
  user: UserInfo
  access_token: string
  refresh_token: string
  token_type: string
}

// 工具相关类型
export type ToolView = 'public' | 'favorites'

export interface ToolDeployment {
  kind: string
  executor_type?: string | null
}

export interface Tool {
  id: string  // UUID
  name: string
  slug: string
  description?: string
  category_id?: string
  icon?: string
  icon_url?: string
  category?: string  // 分类名称
  tags: Tag[]
  status: 'draft' | 'published' | 'disabled' | 'deprecated'
  is_public?: boolean
  // 原有字段
  current_version_id?: string
  current_version?: ToolVersion
  usage_count: number
  view_count: number
  favorite_count: number
  statistics?: {
    usage_count: number
    view_count: number
    favorite_count: number
    success_rate?: number
    avg_execution_time?: number
    last_used_at?: string | null
    last_updated_at?: string
  }
  gpu_required: boolean
  gpu_memory_mb?: number
  timeout_sec?: number
  owner_id?: string
  is_favorited?: boolean  // 额外字段，由API返回
  contract?: ToolContract | null
  deployment?: ToolDeployment | null
  created_at: string
  updated_at?: string
  // 兼容旧代码的字段
  version?: string
  run_count?: number
}

export interface ToolOptionSummary {
  id: Tool['id']
  slug: Tool['slug']
  name: Tool['name']
  description?: Tool['description']
  category_id?: Tool['category_id']
  category?: Tool['category']
  tags?: Tag[]
  icon?: Tool['icon']
  icon_url?: Tool['icon_url']
  status: Tool['status']
  is_public?: Tool['is_public']
  deployment?: ToolDeployment | null
  contract?: ToolContract | null
}

export interface ToolSchema {
  type: 'object'
  properties: Record<string, SchemaProperty>
  required?: string[]
}

export type SchemaValueType =
  | 'string'
  | 'number'
  | 'integer'
  | 'boolean'
  | 'file'
  | 'select'
  | 'array'
  | 'object'
  | 'null'

export interface SchemaProperty {
  type?: SchemaValueType | SchemaValueType[]
  title?: string
  description?: string
  default?: unknown
  enum?: unknown[]
  format?: 'textarea' | 'fasta' | 'pdb' | 'email' | 'url' | 'uri' | 'file'
  accept?: string
  hidden?: boolean
  readOnly?: boolean
  disabled?: boolean
  hint?: string
  minLength?: number
  maxLength?: number
  minimum?: number
  maximum?: number
  // 嵌套对象支持
  properties?: Record<string, SchemaProperty>
  required?: string[]
  // 数组类型支持
  items?: {
    type?: SchemaValueType | SchemaValueType[]
    enum?: unknown[]
  }
  // 扁平化元数据
  _parentKey?: string
  _originalKey?: string
  _platformManaged?: boolean
}

export interface ToolReference {
  title: string
  url: string
  authors?: string
  year?: number
}

export interface ToolContractVersion {
  id?: string | null
  version?: string | null
  is_active?: boolean | null
  deprecated?: boolean | null
}

export interface ToolContractExecutor {
  type: string
  timeout_sec?: number | null
}

export interface ToolCapabilityInput {
  semantic_type: string
  field: string
  required?: boolean
  accepted_extensions?: string[]
}

export interface ToolCapabilityOutputMatch {
  extension?: string | null
  filename_contains_any?: string[]
  content_type?: string | null
  type?: string | null
  name?: string | null
}

export interface ToolCapabilityOutput {
  semantic_type: string
  source: 'output_files' | 'output_data' | 'artifact'
  match?: ToolCapabilityOutputMatch | null
  path?: string | null
  required?: boolean
}

export interface ToolContractCapability {
  enabled: boolean
  capability?: string | null
  stage?: string | null
  inputs: ToolCapabilityInput[]
  outputs: ToolCapabilityOutput[]
  defaults: Record<string, unknown>
  virtual?: boolean
}

export interface ToolContractValidation {
  status: 'valid' | 'invalid'
  errors: string[]
}

export interface ToolContract {
  contract_version: string
  id?: string | null
  slug: string
  name: string
  description?: string | null
  status: Tool['status'] | 'virtual' | string
  is_public?: boolean | null
  version?: ToolContractVersion | null
  executor: ToolContractExecutor
  resource_profile?: Record<string, unknown>
  schema: {
    input: ToolSchema
    output: ToolSchema
  }
  capability: ToolContractCapability
  artifacts?: {
    inputs?: Array<{
      name: string
      title?: string | null
      description?: string | null
      type: string
      required?: boolean
      role_preferences?: string[]
      required_roles?: string[]
      readiness_policy?: string | null
      suggested_preparation_tool?: string | null
    }>
    outputs?: Array<{
      name: string
      type: string
      cardinality?: 'one' | 'many'
      required?: boolean
      provided_roles?: string[]
    }>
  }
  validation: ToolContractValidation
}

export interface Category {
  id: string
  name: string
  slug: string
  description?: string
  sort_order: number
  is_enabled?: boolean
  tool_count?: number
  count?: number
}

export interface WorkbenchGroupTool {
  id: string
  name: string
  slug: string
  description?: string
  category_id?: string
  category?: string
  tags?: Tag[]
  icon?: string
  icon_url?: string
  status: Tool['status']
  is_public?: boolean
  deployment?: ToolDeployment | null
  is_recommended: boolean
  sort_order: number
  contract?: ToolContract | null
}

export interface WorkbenchGroup {
  id: string
  name: string
  slug: string
  description?: string
  sort_order: number
  is_enabled?: boolean
  tools: WorkbenchGroupTool[]
  created_at?: string
  updated_at?: string
}

export interface WorkflowDefinitionNode {
  id: string
  kind?: 'input' | 'tool' | string
  type?: string
  semantic_type?: string
  tool_id?: string
  tool_slug?: string
  tool_version?: ToolContractVersion | null
  semantic_inputs?: Record<string, string>
  semantic_outputs?: string[]
  params?: Record<string, unknown>
  [key: string]: unknown
}

export interface WorkflowDefinitionEdge {
  source: string
  target: string
  source_output?: string
  target_input?: string
  [key: string]: unknown
}

export interface WorkflowDefinition {
  nodes: WorkflowDefinitionNode[]
  edges: WorkflowDefinitionEdge[]
  task_bindings_by_node?: Record<string, string>
  [key: string]: unknown
}

export interface WorkflowRun {
  id: string
  owner_id: string
  workflow_definition_id: string
  project_id?: string | null
  name: string
  status: 'pending' | 'running' | 'waiting_task' | 'success' | 'failure' | 'canceled' | string
  definition: WorkflowDefinition
  input_files: Record<string, string>
  execution_order: string[]
  node_states: Record<string, WorkflowRunNodeState>
  artifact_lineage: Record<string, unknown>
  error_message?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at: string
  updated_at: string
}

export interface WorkflowRunMissingOutputMatch {
  extension?: string | null
  filename_contains_any: string[]
  content_type?: string | null
}

export interface WorkflowRunMissingOutput {
  semantic_type: string
  source: string
  path?: string | null
  required: boolean
  match: WorkflowRunMissingOutputMatch
}

export interface WorkflowRunNodeState {
  status: string
  tool_id?: string | null
  tool_slug?: string | null
  tool_version_id?: string | null
  tool_version?: ToolContractVersion | null
  semantic_inputs?: Record<string, unknown>
  params?: Record<string, unknown>
  input_file_ids?: string[]
  output_file_ids?: string[]
  semantic_outputs?: Record<string, unknown>
  missing_outputs?: WorkflowRunMissingOutput[]
  binding_decisions?: Record<string, ArtifactBindingDecision>
  blocked_reason?: string | null
  task_id?: string | null
  error_message?: string | null
  started_at?: string | null
  finished_at?: string | null
}

export interface WorkflowRunCreateParams {
  name?: string
  input_files: Record<string, string>
  params?: Record<string, unknown>
}

export interface WorkbenchGroupMapping {
  id: string
  tool_id: string
  group_id: string
  tool_name: string
  tool_slug: string
  group_name: string
  sort_order: number
  is_recommended: boolean
  is_enabled: boolean
  created_at?: string
  updated_at?: string
}

export interface Tag {
  id: string  // UUID
  name: string
  description?: string
  color: string
  sort_order: number
  created_at?: string
  updated_at?: string
}

export interface ToolVersion {
  id: string  // UUID
  tool_id: string
  version: string
  changelog?: string
  notes?: string
  // 管理员/内部接口返回运行时配置；公开工具接口只返回版本元数据。
  config?: Record<string, unknown>  // 包含 input_schema, output_schema 等
  tool_package?: Record<string, unknown>
  is_active: boolean
  deprecated: boolean
  created_at?: string
  updated_at?: string
}

export interface ToolExampleFile {
  field: string
  path: string
  filename: string
  size_bytes?: number
  content_type?: string
  exists: boolean
  previewable: boolean
}

export interface ToolExample {
  name: string
  description?: string
  params: Record<string, unknown>
  input_files: ToolExampleFile[]
}

export interface ToolExampleApplyResult {
  params: Record<string, unknown>
  files: Record<string, FileUploadResponse>
}

export interface ToolExampleFilePreview {
  field: string
  filename: string
  content_type?: string
  content?: string
  truncated: boolean
  previewable: boolean
}

export interface RelatedTool {
  id: string
  name: string
  description?: string
  icon?: string
  usage_count: number
  favorite_count: number
}

// 任务相关类型（docs/03 §3.4 八态：pending=已创建、queued=排队中、running、success、failure、timeout、canceled）
export type TaskStatus =
  | 'pending'
  | 'rejected'
  | 'queued'
  | 'running'
  | 'success'
  | 'failure'
  | 'timeout'
  | 'canceled'

export interface TaskInput {
  params: Record<string, unknown>
  file_ids: string[]
  input_bindings?: Record<string, string>
}

export interface TaskOutput {
  result: Record<string, unknown> | null
  file_ids: string[]
  output_type: string
}

export interface TaskResourceSnapshot {
  executor_type?: string | null
  gpu_required: boolean
  gpu_memory_mb: number
  timeout_sec: number
  resource_profile: Record<string, unknown>
}

export interface TaskResourceAdmissionInfo {
  status: 'admitted' | 'unknown' | 'rejected' | string
  worker_id?: string | null
  reason?: string | null
  queue?: string | null
}

export interface TaskResourceReservationInfo {
  worker_id: string
  lease_id?: string
  ttl_seconds?: number
  status?: 'reserved' | 'claimed' | 'released' | 'release_failed' | 'not_found' | string
  release_reason?: string
  release_result?: 'deleted' | 'already_absent' | string
  released_at?: string
  release_error?: string
}

export interface TaskDispatchInfo {
  mode: 'direct' | 'celery' | string
  queue?: string | null
  queue_priority?: number
  resource_admission?: TaskResourceAdmissionInfo | null
  resource_reservation?: TaskResourceReservationInfo | null
}

export interface TaskFailureDiagnosticsPayload {
  error_message?: string
  stdout?: string
  stderr?: string
  standard_artifact_message?: string
}

export interface TaskResourceWaitStatus {
  reason: string
  category?: 'gpu' | 'quota' | 'worker_capacity' | 'scheduler' | 'resource' | string
  scope?: 'user' | 'project' | string | null
  dimension?: string | null
  legacy_reason?: string | null
  retry_count: number
  next_attempt_at?: string | null
}

export interface TaskResourceWaitStats {
  total: number
  by_category: Record<string, number>
  by_reason: Record<string, number>
}

export interface ArtifactBindingDecision {
  status: 'ready' | 'needs_preparation' | 'needs_conversion' | 'invalid' | string
  input_name?: string | null
  standard_type?: string | null
  selected_role?: string | null
  selected_file_id?: string | null
  artifact_version_id?: string | null
  reason?: string | null
  suggested_tool_slug?: string | null
}

export interface Task {
  id: string
  name?: string
  tool_id: string  // UUID
  tool_name?: string  // 工具名称（API额外返回）
  tool_slug?: string  // 工具标识（API额外返回）
  tool?: Tool
  user_id?: string  // UUID
  user_name?: string
  user_email?: string
  status: TaskStatus
  progress: number
  progress_message?: string
  inputs?: TaskInput
  outputs?: TaskOutput
  error_message?: string
  failure_diagnostics?: TaskFailureDiagnosticsPayload | null
  resource_wait?: TaskResourceWaitStatus | null
  started_at?: string
  finished_at?: string
  completed_at?: string  // 完成时间（兼容旧代码，实际使用finished_at）
  execution_time_sec?: number
  retry_count?: number
  priority?: string
  project_id?: string | null
  input_bindings?: Record<string, string>
  binding_decisions?: Record<string, ArtifactBindingDecision>
  resource_snapshot?: TaskResourceSnapshot | null
  dispatch?: TaskDispatchInfo | null
  created_at: string
  updated_at?: string
  // 兼容旧代码的字段
  input_files?: Array<{
    id?: string | number
    original_name?: string
    filename?: string
    relative_path?: string
    size?: number
    content_type?: string
    url?: string
  }>
  output_data?: unknown
  output_files?: Array<{
    id?: string | number
    original_name?: string
    filename?: string
    relative_path?: string
    size?: number
    content_type?: string
    url?: string
  }>
  artifacts?: TypedArtifact[]
}

export interface TaskCreateParams {
  name?: string
  project_id?: string
  tool_id: string
  tool_version_id?: string
  params: Record<string, unknown>
  file_ids?: string[]
  input_bindings?: Record<string, string>
  standard_input_uploads?: Record<string, string>
  priority?: 'low' | 'normal' | 'high'
}

export interface TaskRunPreparationPreview {
  ready: boolean
  project_id?: string | null
  tool_id: string
  tool_version_id: string
  params: Record<string, unknown>
  file_ids: string[]
  input_bindings: Record<string, string>
  requested_input_bindings: Record<string, string>
  standard_input_uploads: Record<string, string>
  binding_decisions: Record<string, ArtifactBindingDecision>
  blocked_reason?: string | null
  resource_snapshot?: TaskResourceSnapshot | null
}

export interface ToolPreparedSubmissionPayload {
  params: Record<string, unknown>
  file_ids?: string[]
}

export interface TaskLog {
  id: number
  task_id: string
  level: 'info' | 'warning' | 'error'
  message: string
  timestamp: string
}

// 文件相关类型
export interface FileInfo {
  id: string
  filename: string
  content_type?: string
  size_bytes: number
  source_type: string
  is_public: boolean
  created_at: string
  updated_at: string
  expires_at?: string
}

export interface FileUploadResponse {
  id: string
  filename: string
  size_bytes?: number
  content_type?: string
  sha256?: string
  url?: string
}

export interface ArtifactFile {
  id: string
  filename: string
  content_type?: string
  size_bytes: number
  source_type: string
  download_url: string
  task_id: string
  task_name?: string
  tool_id: string
  tool_name: string
  tool_slug: string
  artifact_id?: string | null
  artifact_version_id?: string | null
  standard_artifact_role?: string | null
  standard_artifact_output?: string | null
  semantic_type?: string | null
  semantic_source?: string | null
  created_at: string
  updated_at?: string
}

// GPU 相关类型
export interface GPUInfo {
  index: number
  name: string
  memory_total: number
  memory_used: number
  memory_free: number
  utilization: number
  temperature: number
}

export interface GPUSummary {
  total_gpus: number
  total_memory: number
  used_memory: number
  avg_utilization: number
  gpus: GPUInfo[]
}

// 系统相关类型
export interface SystemHealth {
  status: 'healthy' | 'degraded' | 'unhealthy'
  version: string
  environment: string
  services: Array<{
    name: string
    status: 'healthy' | 'unhealthy' | 'unknown'
    latency_ms?: number
    message?: string
  }>
  timestamp: string
}

export interface SystemStats {
  total_users: number
  total_tools: number
  total_tasks: number
  total_files: number
  pending_tasks: number
  running_tasks: number
  completed_tasks: number
  failed_tasks: number
  sse_subscriptions: number
}

export interface WorkerResourceStatus {
  worker_id: string
  queue?: string | null
  healthy: boolean
  executor_types: string[]
  tiers: string[]
  cpu_capacity?: number | null
  cpu_used: number
  cpu_available?: number | null
  memory_capacity_gb?: number | null
  memory_used_gb: number
  memory_available_gb?: number | null
  parallelism?: number | null
  parallelism_used: number
  parallelism_available?: number | null
  reservation_count: number
  execution_count: number
  gpu_count?: number | null
  gpu_memory_mb?: number | null
}

export interface WorkerResourceStatusResponse {
  status: 'healthy' | 'degraded' | 'unknown' | 'unavailable' | string
  timestamp: string
  total_workers: number
  workers: WorkerResourceStatus[]
  error?: string | null
}

export interface ResourceQuotaScope {
  scope_type: 'user' | 'project' | string
  scope_id: string
  cpu_limit?: number | null
  cpu_used: number
  cpu_available?: number | null
  memory_limit_gb?: number | null
  memory_used_gb: number
  memory_available_gb?: number | null
  parallelism_limit?: number | null
  parallelism_used: number
  parallelism_available?: number | null
  gpu_requested_count: number
  gpu_requested_memory_mb: number
  rejection_counts: Record<string, number>
}

export interface ResourceQuotaStatusResponse {
  enabled: boolean
  timestamp: string
  gpu_scope_quota: string
  scopes: ResourceQuotaScope[]
  error?: string | null
}

export interface SystemInfo {
  app_name: string
  app_version: string
  environment: string
  debug: boolean
  python_version: string
  platform: string
  hostname: string
  database_type: string
  storage_backend: string
  cache_backend: string
  task_queue: string
  cpu_count: number
  memory_total_gb: number
  memory_available_gb: number
  memory_percent: number
  disk_total_gb: number
  disk_free_gb: number
  disk_percent: number
}

export interface SystemConfig {
  environment: string
  debug: boolean
  api_prefix: string
  database: Record<string, unknown>
  storage: Record<string, unknown>
  cache: Record<string, unknown>
  jwt: Record<string, unknown>
  cors_origins: string[]
  log_level: string
}


// 分页相关类型
export interface PaginationParams {
  page?: number
  page_size?: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}


// 工具创建参数
export interface ToolCreateParams {
  name: string
  slug: string
  description?: string
  category_id: string
  icon?: string
  icon_url?: string
  is_public?: boolean
  gpu_required?: boolean
  gpu_memory_mb?: number
  timeout_sec?: number
  tag_ids?: string[]
}
