import type { Task } from '@/types/models'
import { isHistoryTask, isRunningTask } from './status'

export type TaskListTab = 'all' | 'running' | 'history'
export type TaskSystemView = 'all' | 'running' | 'history' | 'needs_attention' | 'recent_results'

export interface TaskListQueryInput {
  tab: TaskListTab
  page: number
  pageSize: number
  projectId?: string
  toolId?: string
  keyword?: string
  createdFrom?: string
  createdTo?: string
}

export interface TaskListQueryParams {
  view: TaskSystemView
  page: number
  page_size: number
  project_id?: string
  tool_id?: string
  keyword?: string
  created_from?: string
  created_to?: string
}

export function taskSystemViewForTab(tab: TaskListTab): TaskSystemView {
  return tab
}

export function buildTaskListQueryParams(input: TaskListQueryInput): TaskListQueryParams {
  const params: TaskListQueryParams = {
    view: taskSystemViewForTab(input.tab),
    page: Math.max(input.page, 1),
    page_size: Math.max(input.pageSize, 1),
  }

  const projectId = input.projectId?.trim()
  if (projectId) params.project_id = projectId

  const toolId = input.toolId?.trim()
  if (toolId) params.tool_id = toolId

  const keyword = input.keyword?.trim()
  if (keyword) params.keyword = keyword

  if (input.tab === 'history') {
    if (input.createdFrom) params.created_from = input.createdFrom
    if (input.createdTo) params.created_to = input.createdTo
  }

  return params
}

export function filterTasksForTab(tasks: Task[], tab: TaskListTab): Task[] {
  if (tab === 'running') return tasks.filter(isRunningTask)
  if (tab === 'history') return tasks.filter(isHistoryTask)
  return tasks
}

export function filterTasksByKeyword(tasks: Task[], keyword: string): Task[] {
  const normalizedKeyword = keyword.trim().toLowerCase()
  if (!normalizedKeyword) return tasks

  return tasks.filter(task => {
    const searchableValues = [task.name, task.tool?.name, task.tool_name, task.id]
    return searchableValues.some(value => value?.toLowerCase().includes(normalizedKeyword))
  })
}

export function paginateTasks(tasks: Task[], page: number, pageSize: number): Task[] {
  const safePage = Math.max(page, 1)
  const safePageSize = Math.max(pageSize, 1)
  const start = (safePage - 1) * safePageSize
  return tasks.slice(start, start + safePageSize)
}
