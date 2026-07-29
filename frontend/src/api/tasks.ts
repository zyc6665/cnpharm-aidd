import { get, post, del, type RequestOptions } from './request'
import type { ApiResponse } from '@/types/api'
import type { Task, TaskCreateParams, TaskLog, TaskStatus, PaginatedResponse, PaginationParams } from '@/types/models'

export interface TaskListParams extends PaginationParams {
  status?: TaskStatus
  tool_id?: string
  keyword?: string
}

export const TERMINAL_TASK_STATUSES: readonly TaskStatus[] = ['success', 'failure', 'canceled']

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

// 创建任务
export const createTask = (data: TaskCreateParams): Promise<ApiResponse<Task>> => {
  return post<Task>('/tasks', data)
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
export const getTaskLogs = (
  id: string,
  options?: RequestOptions
): Promise<ApiResponse<PaginatedResponse<TaskLog>>> => {
  return get<PaginatedResponse<TaskLog>>(`/tasks/${id}/logs`, undefined, options)
}
