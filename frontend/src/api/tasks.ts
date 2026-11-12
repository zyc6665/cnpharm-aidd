import { get, post, del, type RequestOptions } from './request'
import type { ApiResponse } from '@/types/api'
import { terminalStatuses } from '@/domain/tasks/status'
import type { TaskCountQueryParams, TaskSystemView, TaskViewCounts } from '@/domain/tasks/listing'
import type {
  Task,
  TaskCreateParams,
  TaskLog,
  TaskRunPreparationPreview,
  TaskResourceWaitStats,
  TaskStatus,
  PaginatedResponse,
  PaginationParams
} from '@/types/models'

export interface TaskListParams extends PaginationParams {
  view?: TaskSystemView
  status?: TaskStatus
  tool_id?: string
  /** 按工具 slug 集合筛选（数组以重复参数下发），设计任务页按类别拉取。 */
  tool_slugs?: string[]
  keyword?: string
  project_id?: string
  created_from?: string
  created_to?: string
  workflow_run_id?: string
  workflow_definition_id?: string
  workflow_node_id?: string
  resource_wait_category?: string
  resource_wait_scope?: 'user' | 'project' | string
}

/** 终态任务集合，统一取自 `domain/tasks/status`，避免各处硬编码漏状态。 */
export const TERMINAL_TASK_STATUSES: readonly TaskStatus[] = terminalStatuses

export function isTaskTerminalStatus(status: TaskStatus): boolean {
  return TERMINAL_TASK_STATUSES.includes(status)
}

// 获取任务列表
export const getTaskList = (
  params?: TaskListParams,
  options?: RequestOptions
): Promise<ApiResponse<PaginatedResponse<Task>>> => {
  return get<PaginatedResponse<Task>, TaskListParams>('/tasks', params, options)
}

export const getTaskCounts = (
  params?: TaskCountQueryParams,
  options?: RequestOptions
): Promise<ApiResponse<TaskViewCounts>> => {
  return get<TaskViewCounts, TaskCountQueryParams>('/tasks/counts', params, options)
}

export const getResourceWaitStats = (
  options?: RequestOptions
): Promise<ApiResponse<TaskResourceWaitStats>> => {
  return get<TaskResourceWaitStats>('/tasks/resource-wait-stats', undefined, options)
}

// 创建任务
export const createTask = (data: TaskCreateParams): Promise<ApiResponse<Task>> => {
  return post<Task>('/tasks', data)
}

// 预览任务运行准备，不创建任务
export const prepareTaskRun = (data: TaskCreateParams): Promise<ApiResponse<TaskRunPreparationPreview>> => {
  return post<TaskRunPreparationPreview>('/tasks/prepare-preview', data)
}

// 获取任务详情
export const getTaskDetail = (id: string, options?: RequestOptions): Promise<ApiResponse<Task>> => {
  return get<Task>(`/tasks/${id}`, undefined, options)
}

// 删除任务
export const deleteTask = (id: string): Promise<ApiResponse<null>> => {
  return del<null>(`/tasks/${id}`)
}

// 取消任务
export const cancelTask = (id: string): Promise<ApiResponse<Task>> => {
  return post<Task>(`/tasks/${id}/cancel`)
}

// 重试任务
export const retryTask = (id: string): Promise<ApiResponse<Task>> => {
  return post<Task>(`/tasks/${id}/retry`)
}

// 获取任务日志
// `order: 'desc'` 表示"从最新一条开始翻页"——长任务动辄上千行，取第 1 页升序
// 只会拿到任务刚开始那几行，界面看起来就是"日志不动了"。
export interface TaskLogQuery extends Record<string, unknown> {
  page?: number
  page_size?: number
  level?: string
  order?: 'asc' | 'desc'
}

export const getTaskLogs = (
  id: string,
  params?: TaskLogQuery,
  options?: RequestOptions
): Promise<ApiResponse<PaginatedResponse<TaskLog>>> => {
  return get<PaginatedResponse<TaskLog>>(`/tasks/${id}/logs`, params, options)
}
