import { get, post, put, patch, del } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  Tool, Category, Tag, ToolVersion, PaginatedResponse, PaginationParams,
  ToolView, ToolCreateParams, ToolOptionSummary, WorkbenchGroup, WorkbenchGroupMapping,
  ToolExample, ToolExampleApplyResult, ToolExampleFilePreview
} from '@/types/models'

export interface ToolListParams extends PaginationParams {
  category?: string  // 分类名称
  tag?: string       // 标签名称
  search?: string    // 搜索关键词
  status?: string    // 状态筛选（管理员）
  view?: ToolView    // 视图类型：public/favorites
}

export interface ToolImportConfigParams {
  config: Record<string, unknown>
  category_id?: string
  publish?: boolean
}

export interface ToolImportConfigResult {
  created_new_tool: boolean
  tool: Tool
  version: ToolVersion
}

export interface RemoteToolRegisterParams {
  base_url: string
  category_id: string
  run_smoke_test?: boolean
  publish_on_success?: boolean
  icon?: string
  icon_url?: string
  is_public?: boolean
  timeout_sec?: number
}

export interface RemoteToolStageDiagnostic {
  name: string
  status: 'success' | 'failure' | 'warning'
  message: string
  detail?: Record<string, unknown> | null
}

export interface RemoteToolRegisterResult {
  created_new_tool: boolean
  tool: Tool
  version: ToolVersion
  manifest_sha256: string
  stages: RemoteToolStageDiagnostic[]
  smoke_test_task_id?: string | null
}

export interface ToolTemplateSummary {
  template_key: string
  slug: string
  name: string
  version: string
  description: string
  family: string
  executor_types: Array<'remote_api' | 'docker_image' | 'python_script' | 'ssh_job'>
  capability: string
  stage: string
  inputs: Array<Record<string, unknown>>
  outputs: Array<Record<string, unknown>>
  implementation: {
    source: 'open_source' | 'internal_service'
    provider: string
    runtime: string
    project_url?: string | null
    recommended_executor: 'remote_api' | 'docker_image' | 'python_script' | 'ssh_job'
    notes?: string | null
  }
  resource_profile: Record<string, unknown>
}

export interface ToolTemplateDraftParams {
  executor_type: 'remote_api' | 'docker_image' | 'python_script' | 'ssh_job'
  executor_config: Record<string, unknown>
  category_id?: string
  publish?: boolean
}

function toToolOptionSummary(tool: Tool): ToolOptionSummary {
  return {
    id: tool.id,
    slug: tool.slug,
    name: tool.name,
    description: tool.description,
    icon: tool.icon,
    icon_url: tool.icon_url,
    status: tool.status,
    is_public: tool.is_public
  }
}

// 获取工具列表
export const getToolList = (params?: ToolListParams): Promise<ApiResponse<PaginatedResponse<Tool>>> => {
  return get<PaginatedResponse<Tool>, ToolListParams>('/tools', params)
}

export const getWorkflowToolOptions = async (): Promise<ApiResponse<ToolOptionSummary[]>> => {
  const response = await getToolList({
    view: 'public',
    page: 1,
    page_size: 100
  })

  return {
    ...response,
    data: response.data.items.map(toToolOptionSummary)
  }
}

export const getWorkbenchGroups = (): Promise<ApiResponse<WorkbenchGroup[]>> => {
  return get<WorkbenchGroup[]>('/tools/workbench-groups')
}

// 获取工具详情
export const getToolDetail = (id: string): Promise<ApiResponse<Tool>> => {
  return get<Tool>(`/tools/${id}`)
}

export const getToolExample = (id: string): Promise<ApiResponse<ToolExample | null>> => {
  return get<ToolExample | null>(`/tools/${id}/example`)
}

export const applyToolExample = (id: string): Promise<ApiResponse<ToolExampleApplyResult>> => {
  return post<ToolExampleApplyResult>(`/tools/${id}/example/apply`)
}

export const previewToolExampleFile = (
  id: string,
  field: string
): Promise<ApiResponse<ToolExampleFilePreview>> => {
  return get<ToolExampleFilePreview>(`/tools/${id}/example/files/${encodeURIComponent(field)}/preview`)
}

// 创建工具（管理员）
export const createTool = (data: ToolCreateParams): Promise<ApiResponse<Tool>> => {
  return post<Tool>('/tools', data)
}

// 导入工具配置（管理员）
export const importToolConfig = (data: ToolImportConfigParams): Promise<ApiResponse<ToolImportConfigResult>> => {
  return post<ToolImportConfigResult>('/tools/import-config', data)
}

// 注册 remote-tool.v1 自描述服务（管理员）
export const registerRemoteTool = (
  data: RemoteToolRegisterParams
): Promise<ApiResponse<RemoteToolRegisterResult>> => {
  return post<RemoteToolRegisterResult>('/tools/register-remote', data)
}

export const listToolTemplates = (): Promise<ApiResponse<ToolTemplateSummary[]>> => {
  return get<ToolTemplateSummary[]>('/tool-templates')
}

export const createToolDraftFromTemplate = (
  templateKey: string,
  data: ToolTemplateDraftParams
): Promise<ApiResponse<ToolImportConfigResult>> => {
  return post<ToolImportConfigResult>(`/tool-templates/${templateKey}/draft`, data)
}

// 更新工具（管理员）
export const updateTool = (id: string, data: Partial<Tool>): Promise<ApiResponse<Tool>> => {
  return put<Tool>(`/tools/${id}`, data)
}

// 删除工具（管理员）
export const deleteTool = (id: string): Promise<ApiResponse<null>> => {
  return del<null>(`/tools/${id}`)
}

// 发布工具（管理员）
export const publishTool = (id: string): Promise<ApiResponse<null>> => {
  return post<null>(`/tools/${id}/publish`)
}

// 收藏工具
export const favoriteTool = (id: string): Promise<ApiResponse<null>> => {
  return post<null>(`/tools/${id}/favorite`)
}

// 取消收藏
export const unfavoriteTool = (id: string): Promise<ApiResponse<null>> => {
  return del<null>(`/tools/${id}/favorite`)
}

// 获取工具版本列表
export const getToolVersions = (id: string): Promise<ApiResponse<ToolVersion[]>> => {
  return get<ToolVersion[]>(`/tools/${id}/versions`)
}

// 创建工具版本（管理员）
export const createToolVersion = (id: string, data: {
  version: string
  changelog?: string
  notes?: string
  config: Record<string, unknown>
  is_active?: boolean
}): Promise<ApiResponse<ToolVersion>> => {
  return post<ToolVersion>(`/tools/${id}/versions`, data)
}

// 获取分类列表
export const getCategories = (): Promise<ApiResponse<Category[]>> => {
  return get<Category[]>('/tools/categories')
}

// 获取标签列表
export const getTags = (): Promise<ApiResponse<Tag[]>> => {
  return get<Tag[]>('/tools/tags')
}

// 创建标签 (管理员)
export const createTag = (data: { name: string; color?: string; description?: string }): Promise<ApiResponse<Tag>> => {
  return post<Tag>('/tools/tags', data)
}

// ==================== 管理员分类接口 ====================

export const adminGetToolCategories = (): Promise<ApiResponse<Category[]>> => {
  return get<Category[]>('/admin/tool-categories')
}

export const adminGetWorkbenchGroups = (): Promise<ApiResponse<WorkbenchGroup[]>> => {
  return get<WorkbenchGroup[]>('/admin/workbench-groups')
}

export const adminCreateWorkbenchGroup = (data: {
  name: string
  slug: string
  description?: string
  sort_order?: number
  is_enabled?: boolean
}): Promise<ApiResponse<WorkbenchGroup>> => {
  return post<WorkbenchGroup>('/admin/workbench-groups', data)
}

export const adminUpdateWorkbenchGroup = (id: string, data: {
  name?: string
  slug?: string
  description?: string
  sort_order?: number
  is_enabled?: boolean
}): Promise<ApiResponse<WorkbenchGroup>> => {
  return put<WorkbenchGroup>(`/admin/workbench-groups/${id}`, data)
}

export const adminReorderWorkbenchGroups = (group_ids: string[]): Promise<ApiResponse<WorkbenchGroup[]>> => {
  return post<WorkbenchGroup[]>('/admin/workbench-groups/reorder', { group_ids })
}

export const adminDeleteWorkbenchGroup = (id: string): Promise<ApiResponse<null>> => {
  return del<null>(`/admin/workbench-groups/${id}`)
}

export interface AdminWorkbenchGroupMappingListParams extends PaginationParams {
  search?: string
  group_id?: string
}

export const adminGetWorkbenchGroupMappings = (
  params?: AdminWorkbenchGroupMappingListParams
): Promise<ApiResponse<PaginatedResponse<WorkbenchGroupMapping>>> => {
  return get<PaginatedResponse<WorkbenchGroupMapping>, AdminWorkbenchGroupMappingListParams>(
    '/admin/workbench-group-mappings',
    params
  )
}

export const adminCreateWorkbenchGroupMapping = (data: {
  tool_id: string
  group_id: string
  sort_order?: number
  is_recommended?: boolean
  is_enabled?: boolean
}): Promise<ApiResponse<WorkbenchGroupMapping>> => {
  return post<WorkbenchGroupMapping>('/admin/workbench-group-mappings', data)
}

export const adminUpdateWorkbenchGroupMapping = (id: string, data: {
  tool_id?: string
  group_id?: string
  sort_order?: number
  is_recommended?: boolean
  is_enabled?: boolean
}): Promise<ApiResponse<WorkbenchGroupMapping>> => {
  return put<WorkbenchGroupMapping>(`/admin/workbench-group-mappings/${id}`, data)
}

export const adminDeleteWorkbenchGroupMapping = (id: string): Promise<ApiResponse<null>> => {
  return del<null>(`/admin/workbench-group-mappings/${id}`)
}

export const adminCreateToolCategory = (data: {
  name: string
  slug: string
  description?: string
  sort_order?: number
  is_enabled?: boolean
}): Promise<ApiResponse<Category>> => {
  return post<Category>('/admin/tool-categories', data)
}

export const adminUpdateToolCategory = (id: string, data: {
  name?: string
  slug?: string
  description?: string
  sort_order?: number
}): Promise<ApiResponse<Category>> => {
  return put<Category>(`/admin/tool-categories/${id}`, data)
}

export const adminToggleToolCategory = (id: string, is_enabled: boolean): Promise<ApiResponse<Category>> => {
  return patch<Category>(`/admin/tool-categories/${id}/status`, { is_enabled })
}

export const adminReorderToolCategories = (category_ids: string[]): Promise<ApiResponse<Category[]>> => {
  return post<Category[]>('/admin/tool-categories/reorder', { category_ids })
}

export const adminDeleteToolCategory = (id: string): Promise<ApiResponse<null>> => {
  return del<null>(`/admin/tool-categories/${id}`)
}
