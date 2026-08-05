import type { Task } from '@/types/models'
import { isHistoryTask, isRunningTask } from './status'

export type TaskListTab = 'all' | 'running' | 'history'

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
