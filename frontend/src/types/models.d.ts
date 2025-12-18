// 用户相关类型
export interface UserInfo {
  id: number
  username: string
  email: string
  role: 'user' | 'vip' | 'admin' | 'guest'
  avatar?: string
  is_active: boolean
  credits: number
  member_expire_at?: string
  invitation_code?: string
  created_at: string
  updated_at: string
}

export interface LoginParams {
  username: string
  password: string
  remember?: boolean
}

export interface RegisterParams {
  username: string
  email: string
  password: string
  code: string
  invitation_code?: string
}

export interface GuestLoginResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface LoginResponse extends AuthTokens {
  user: UserInfo
  credits: number
}

// 积分相关类型
export type CreditTransactionType = 'recharge' | 'consume' | 'reward' | 'refund' | 'signup' | 'signin' | 'invite'

export interface CreditTransaction {
  id: number
  user_id: number
  type: CreditTransactionType
  amount: number
  balance: number
  description: string
  created_at: string
}

export interface CreditPackage {
  id: string
  name: string
  credits: number
  price: number
  bonus?: number
  recommended?: boolean
}

// 会员相关类型
export type MembershipPlan = 'free' | 'basic' | 'standard' | 'premium'

export interface MembershipInfo {
  id: string
  name: string
  price: number
  period: string
  features: string[]
  credits_monthly: number
  discount: number
  recommended?: boolean
}

// 签到相关类型
export interface SignInInfo {
  signed_days: number
  already_signed: boolean
  today_reward: number
  streak_bonus: boolean
}

// 工具相关类型
export type ToolView = 'public' | 'custom' | 'favorite'

export interface Tool {
  id: number
  name: string
  slug: string
  description: string
  icon?: string
  category_id: number
  category?: Category
  tags: Tag[]
  status: 'draft' | 'published' | 'deprecated'
  version: string
  versions?: string[]
  input_schema: ToolSchema
  output_schema?: ToolSchema
  config?: Record<string, unknown>
  favorite_count: number
  run_count: number
  avg_duration?: number
  credits: number
  estimated_time?: string
  is_favorited?: boolean
  is_free?: boolean
  creator?: string
  introduction?: string
  features?: string[]
  steps?: string[]
  input_formats?: string[]
  output_formats?: string[]
  references?: ToolReference[]
  github_url?: string
  paper_url?: string
  doc_url?: string
  example_params?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ToolSchema {
  type: 'object'
  properties: Record<string, SchemaProperty>
  required?: string[]
}

export interface SchemaProperty {
  type: 'string' | 'number' | 'boolean' | 'file' | 'select' | 'array'
  title: string
  description?: string
  default?: unknown
  enum?: unknown[]
  format?: 'textarea' | 'fasta' | 'pdb' | 'email' | 'url'
  accept?: string
  minLength?: number
  maxLength?: number
  minimum?: number
  maximum?: number
}

export interface ToolReference {
  title: string
  url: string
  authors?: string
  year?: number
}

export interface Category {
  id: number
  name: string
  slug: string
  description?: string
  icon?: string
  tool_count?: number
}

export interface Tag {
  id: number
  name: string
  color?: string
}

export interface ToolVersion {
  id: number
  tool_id: number
  version: string
  changelog?: string
  is_current: boolean
  created_at: string
}

export interface RelatedTool {
  id: number
  name: string
  description: string
  icon?: string
  credits: number
  run_count: number
}

// 任务相关类型
export type TaskStatus = 'pending' | 'running' | 'success' | 'failure' | 'canceled'

export interface Task {
  id: string
  tool_id: number
  tool?: Tool
  user_id: number
  status: TaskStatus
  progress: number
  input_params: Record<string, unknown>
  input_files?: FileInfo[]
  output_data?: Record<string, unknown>
  output_files?: FileInfo[]
  error_message?: string
  started_at?: string
  completed_at?: string
  created_at: string
  updated_at: string
}

export interface TaskCreateParams {
  tool_id: number
  input_params: Record<string, unknown>
  input_file_ids?: number[]
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
  id: number
  filename: string
  original_name: string
  mime_type: string
  size: number
  hash?: string
  url?: string
  created_at: string
  expires_at?: string
}

export interface FileUploadResponse {
  id: number
  filename: string
  url: string
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
  database: boolean
  cache: boolean
  storage: boolean
  gpu: boolean
  timestamp: string
}

export interface SystemStats {
  total_users: number
  total_tools: number
  total_tasks: number
  total_storage: number
  active_tasks: number
  gpu_usage: GPUSummary
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

// WebSocket 消息类型
export interface WSMessage {
  type: 'progress' | 'status' | 'log' | 'completed' | 'failed' | 'pong'
  task_id?: string
  progress?: number
  status?: TaskStatus
  message?: string
  data?: unknown
}
