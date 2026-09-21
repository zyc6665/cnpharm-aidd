import type { Task } from '@/types/models'
import { isHistoryTask, isRunningTask } from './status'

export type TaskListTab = 'all' | 'running' | 'history' | 'needs_attention'
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
  workflowRunId?: string
  workflowDefinitionId?: string
  workflowNodeId?: string
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
  workflow_run_id?: string
  workflow_definition_id?: string
  workflow_node_id?: string
  remote_recovery_alerted?: boolean
}

export interface TaskCountQueryParams {
  project_id?: string
  tool_id?: string
  keyword?: string
  created_from?: string
  created_to?: string
  workflow_run_id?: string
  workflow_definition_id?: string
  workflow_node_id?: string
}

export type TaskViewCounts = Record<TaskSystemView, number>
export type TaskWorkflowScopeKey = 'run' | 'definition' | 'node'
export type TaskListEmptyTextKey =
  | 'tasks.noTasks'
  | 'tasks.noRunningTasks'
  | 'tasks.noAttentionTasks'
  | 'tasks.noHistoryTasks'

export interface TaskListViewCounts {
  all: number
  running: number
  attention: number
  history: number
}

export interface TaskListViewModelInput {
  tasks: Task[]
  tab: TaskListTab
  keyword: string
  counts: TaskViewCounts
}

export interface TaskListViewModel {
  displayTasks: Task[]
  runningTasks: Task[]
  hasDisplayItems: boolean
  counts: TaskListViewCounts
}

export interface TaskWorkflowScopePart {
  key: TaskWorkflowScopeKey
  value: string
}

export function taskSystemViewForTab(tab: TaskListTab): TaskSystemView {
  return tab
}

export function taskListTabFromQueryParam(
  value: unknown,
  fallback: TaskListTab = 'all'
): TaskListTab {
  const rawValue = Array.isArray(value) ? value[0] : value
  switch (rawValue) {
    case 'all':
    case 'running':
    case 'history':
    case 'needs_attention':
      return rawValue
    default:
      return fallback
  }
}

export function getTaskListEmptyTextKey(tab: TaskListTab): TaskListEmptyTextKey {
  if (tab === 'running') return 'tasks.noRunningTasks'
  if (tab === 'needs_attention') return 'tasks.noAttentionTasks'
  if (tab === 'history') return 'tasks.noHistoryTasks'
  return 'tasks.noTasks'
}

export function buildTaskWorkflowScopeParts(input: {
  workflowRunId?: string
  workflowDefinitionId?: string
  workflowNodeId?: string
}): TaskWorkflowScopePart[] {
  return [
    taskWorkflowScopePart('run', input.workflowRunId),
    taskWorkflowScopePart('definition', input.workflowDefinitionId),
    taskWorkflowScopePart('node', input.workflowNodeId),
  ].filter((part): part is TaskWorkflowScopePart => Boolean(part))
}

function taskWorkflowScopePart(
  key: TaskWorkflowScopeKey,
  value: string | undefined
): TaskWorkflowScopePart | null {
  const normalizedValue = value?.trim()
  return normalizedValue ? { key, value: normalizedValue } : null
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

  const workflowRunId = input.workflowRunId?.trim()
  if (workflowRunId) params.workflow_run_id = workflowRunId

  const workflowDefinitionId = input.workflowDefinitionId?.trim()
  if (workflowDefinitionId) params.workflow_definition_id = workflowDefinitionId

  const workflowNodeId = input.workflowNodeId?.trim()
  if (workflowNodeId) params.workflow_node_id = workflowNodeId

  if (input.tab === 'history') {
    if (input.createdFrom) params.created_from = input.createdFrom
    if (input.createdTo) params.created_to = input.createdTo
  }

  return params
}

export function buildTaskCountQueryParams(input: TaskListQueryInput): TaskCountQueryParams {
  const params: TaskCountQueryParams = {}

  const projectId = input.projectId?.trim()
  if (projectId) params.project_id = projectId

  const toolId = input.toolId?.trim()
  if (toolId) params.tool_id = toolId

  const keyword = input.keyword?.trim()
  if (keyword) params.keyword = keyword

  const workflowRunId = input.workflowRunId?.trim()
  if (workflowRunId) params.workflow_run_id = workflowRunId

  const workflowDefinitionId = input.workflowDefinitionId?.trim()
  if (workflowDefinitionId) params.workflow_definition_id = workflowDefinitionId

  const workflowNodeId = input.workflowNodeId?.trim()
  if (workflowNodeId) params.workflow_node_id = workflowNodeId

  if (input.tab === 'history') {
    if (input.createdFrom) params.created_from = input.createdFrom
    if (input.createdTo) params.created_to = input.createdTo
  }

  return params
}

export function filterTasksForTab(tasks: Task[], tab: TaskListTab): Task[] {
  if (tab === 'running') return tasks.filter(isRunningTask)
  if (tab === 'history') return tasks.filter(isHistoryTask)
  if (tab === 'needs_attention') return tasks.filter(task => task.status === 'failure')
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

export function buildTaskListViewModel(input: TaskListViewModelInput): TaskListViewModel {
  const displayTasks = filterTasksByKeyword(
    filterTasksForTab(input.tasks, input.tab),
    input.keyword
  )

  return {
    displayTasks,
    runningTasks: displayTasks.filter(isRunningTask),
    hasDisplayItems: displayTasks.length > 0,
    counts: {
      all: input.counts.all,
      running: input.counts.running,
      attention: input.counts.needs_attention,
      history: input.counts.history,
    },
  }
}

export function paginateTasks(tasks: Task[], page: number, pageSize: number): Task[] {
  const safePage = Math.max(page, 1)
  const safePageSize = Math.max(pageSize, 1)
  const start = (safePage - 1) * safePageSize
  return tasks.slice(start, start + safePageSize)
}
