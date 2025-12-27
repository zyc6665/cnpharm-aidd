import { get, post, put, del } from './request'
import type { ApiResponse } from '@/types/api'
import type {
  Tool, Category, Tag, ToolVersion, PaginatedResponse, PaginationParams,
  ToolView, ToolProviderType, ToolReviewStatus, ToolCreateParams,
  ToolReviewRequest, ToolReviewResponse, SetPlatformToolRequest
} from '@/types/models'

export interface ToolListParams extends PaginationParams {
  category?: string  // 分类名称
  tag?: string       // 标签名称
  search?: string    // 搜索关键词
  status?: string    // 状态筛选（管理员）
  provider_type?: ToolProviderType  // 工具来源：platform/user
  view?: ToolView    // 视图类型：public/my/favorites
}

export interface MyToolListParams extends PaginationParams {
  status?: string          // 工具状态
  review_status?: string   // 审核状态
}

// 获取工具列表
export const getToolList = (params?: ToolListParams): Promise<ApiResponse<PaginatedResponse<Tool>>> => {
  return get<PaginatedResponse<Tool>>('/tools', params as Record<string, unknown>)
}

// 获取我的工具列表
export const getMyToolList = (params?: MyToolListParams): Promise<ApiResponse<PaginatedResponse<Tool>>> => {
  return get<PaginatedResponse<Tool>>('/tools/my', params as Record<string, unknown>)
}

// 获取工具详情
export const getToolDetail = (id: string): Promise<ApiResponse<Tool>> => {
  return get<Tool>(`/tools/${id}`)
}

// 创建工具（注册用户可用）
export const createTool = (data: ToolCreateParams): Promise<ApiResponse<Tool>> => {
  return post<Tool>('/tools', data)
}

// 更新工具（所有者/管理员）
export const updateTool = (id: string, data: Partial<Tool>): Promise<ApiResponse<Tool>> => {
  return put<Tool>(`/tools/${id}`, data)
}

// 删除工具（所有者可删除草稿/被拒绝，管理员可删除所有）
export const deleteTool = (id: string): Promise<ApiResponse<null>> => {
  return del<null>(`/tools/${id}`)
}

// 发布工具（所有者/管理员）
export const publishTool = (id: string): Promise<ApiResponse<null>> => {
  return post<null>(`/tools/${id}/publish`)
}

// 提交工具审核
export const submitToolReview = (id: string): Promise<ApiResponse<{ id: string; review_status: string }>> => {
  return post<{ id: string; review_status: string }>(`/tools/${id}/submit-review`)
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

// 创建工具版本（所有者/管理员）
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

// ==================== 管理员接口 ====================

// 审核工具（管理员）
export const adminReviewTool = (id: string, data: ToolReviewRequest): Promise<ApiResponse<ToolReviewResponse>> => {
  return post<ToolReviewResponse>(`/tools/admin/${id}/review`, data)
}

// 设置为平台官方工具（管理员）
export const adminSetPlatformTool = (id: string, data: SetPlatformToolRequest): Promise<ApiResponse<{
  id: string
  provider_type: ToolProviderType
  review_status: ToolReviewStatus
}>> => {
  return post<{ id: string; provider_type: ToolProviderType; review_status: ToolReviewStatus }>(
    `/tools/admin/${id}/set-platform`,
    data
  )
}

// 获取待审核工具列表（管理员）
export const adminGetPendingReviews = (params?: PaginationParams): Promise<ApiResponse<PaginatedResponse<Tool>>> => {
  return get<PaginatedResponse<Tool>>('/tools/admin/pending-reviews', params as Record<string, unknown>)
}
