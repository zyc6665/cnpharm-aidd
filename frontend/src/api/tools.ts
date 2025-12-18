import { get, post, put, del } from './request'
import type { ApiResponse } from '@/types/api'
import type { Tool, Category, Tag, ToolVersion, RelatedTool, PaginatedResponse, PaginationParams, ToolView } from '@/types/models'

export interface ToolListParams extends PaginationParams {
  keyword?: string
  category_id?: number
  tag_ids?: number[]
  status?: string
  view?: ToolView
}

// 获取工具列表（支持三视图）
export const getToolList = (params?: ToolListParams): Promise<ApiResponse<PaginatedResponse<Tool>>> => {
  return get<PaginatedResponse<Tool>>('/tools', params as Record<string, unknown>)
}

// 获取收藏的工具列表
export const getFavoriteTools = (params?: PaginationParams): Promise<ApiResponse<PaginatedResponse<Tool>>> => {
  return get<PaginatedResponse<Tool>>('/tools/favorites', params as Record<string, unknown>)
}

// 获取自定义工具列表
export const getCustomTools = (params?: PaginationParams): Promise<ApiResponse<PaginatedResponse<Tool>>> => {
  return get<PaginatedResponse<Tool>>('/tools/custom', params as Record<string, unknown>)
}

// 获取同类推荐工具
export const getRelatedTools = (id: number, limit?: number): Promise<ApiResponse<RelatedTool[]>> => {
  return get<RelatedTool[]>(`/tools/${id}/related`, { limit: limit || 4 })
}

// 获取热门工具
export const getPopularTools = (limit?: number): Promise<ApiResponse<Tool[]>> => {
  return get<Tool[]>('/tools/popular', { limit: limit || 8 })
}

// 获取最近使用的工具
export const getRecentTools = (limit?: number): Promise<ApiResponse<Tool[]>> => {
  return get<Tool[]>('/tools/recent', { limit: limit || 8 })
}

// 获取工具详情
export const getToolDetail = (id: number): Promise<ApiResponse<Tool>> => {
  return get<Tool>(`/tools/${id}`)
}

// 创建工具 (管理员)
export const createTool = (data: Partial<Tool>): Promise<ApiResponse<Tool>> => {
  return post<Tool>('/tools', data)
}

// 更新工具 (管理员)
export const updateTool = (id: number, data: Partial<Tool>): Promise<ApiResponse<Tool>> => {
  return put<Tool>(`/tools/${id}`, data)
}

// 删除工具 (管理员)
export const deleteTool = (id: number): Promise<ApiResponse<null>> => {
  return del<null>(`/tools/${id}`)
}

// 发布工具 (管理员)
export const publishTool = (id: number): Promise<ApiResponse<Tool>> => {
  return post<Tool>(`/tools/${id}/publish`)
}

// 收藏工具
export const favoriteTool = (id: number): Promise<ApiResponse<null>> => {
  return post<null>(`/tools/${id}/favorite`)
}

// 取消收藏
export const unfavoriteTool = (id: number): Promise<ApiResponse<null>> => {
  return del<null>(`/tools/${id}/favorite`)
}

// 获取工具版本列表
export const getToolVersions = (id: number): Promise<ApiResponse<ToolVersion[]>> => {
  return get<ToolVersion[]>(`/tools/${id}/versions`)
}

// 创建工具版本 (管理员)
export const createToolVersion = (id: number, data: { version: string; changelog?: string }): Promise<ApiResponse<ToolVersion>> => {
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
export const createTag = (data: { name: string; color?: string }): Promise<ApiResponse<Tag>> => {
  return post<Tag>('/tools/tags', data)
}
