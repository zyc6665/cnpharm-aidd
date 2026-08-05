import type { Task, TaskStatus } from '@/types/models'

export type TaskProgressStatus = 'normal' | 'active' | 'exception' | 'success'

const runningStatuses: TaskStatus[] = ['pending', 'running']
const historyStatuses: TaskStatus[] = ['success', 'failure', 'canceled']
const taskStatusSet = new Set<TaskStatus>(['pending', 'running', 'success', 'failure', 'canceled'])

export function normalizeTaskStatus(status?: string): TaskStatus {
  const normalizedStatus = status?.toLowerCase()
  return taskStatusSet.has(normalizedStatus as TaskStatus)
    ? (normalizedStatus as TaskStatus)
    : 'pending'
}

export function getTaskStatusColor(status: TaskStatus): string {
  const colors: Record<TaskStatus, string> = {
    pending: 'orange',
    running: 'processing',
    success: 'success',
    failure: 'error',
    canceled: 'default'
  }

  return colors[status]
}

export function getTaskProgressStatus(status: TaskStatus): TaskProgressStatus {
  if (status === 'running') return 'active'
  if (status === 'failure') return 'exception'
  if (status === 'success') return 'success'
  return 'normal'
}

export function getTaskProgressColor(status: TaskStatus): string {
  if (status === 'running') return '#1890ff'
  if (status === 'failure') return '#ff4d4f'
  return '#52c41a'
}

export function isRunningTask(task: Pick<Task, 'status'>): boolean {
  return runningStatuses.includes(task.status)
}

export function isHistoryTask(task: Pick<Task, 'status'>): boolean {
  return historyStatuses.includes(task.status)
}
