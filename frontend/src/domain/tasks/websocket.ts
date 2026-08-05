import type { TaskLog, TaskStatus, WSMessage } from '@/types/models'
import { isHistoryTask, normalizeTaskStatus } from './status'

export interface TaskWebSocketProgressContext {
  taskId: string
  currentProgress: number
}

export interface TaskWebSocketLogContext {
  taskId: string
  id: number
  timestamp: string
}

export interface TaskWebSocketProgressUpdate {
  taskId: string
  progress: number
  status?: TaskStatus
}

export function isTaskWebSocketMessageForTask(message: WSMessage, taskId: string): boolean {
  return message.task_id === taskId
}

export function resolveTaskWebSocketProgressUpdate(
  message: WSMessage,
  context: TaskWebSocketProgressContext
): TaskWebSocketProgressUpdate | null {
  if (message.type === 'task_progress') {
    return {
      taskId: context.taskId,
      progress: resolveTaskProgressPercent(message),
      status: message.status ? normalizeTaskStatus(message.status) : undefined
    }
  }

  if (message.type === 'task_status' && message.status) {
    return {
      taskId: context.taskId,
      progress: context.currentProgress,
      status: normalizeTaskStatus(message.status)
    }
  }

  if (message.type === 'task_complete') {
    return {
      taskId: context.taskId,
      progress: 100,
      status: 'success'
    }
  }

  if (message.type === 'task_error') {
    return {
      taskId: context.taskId,
      progress: context.currentProgress,
      status: 'failure'
    }
  }

  return null
}

export function resolveTaskWebSocketLog(
  message: WSMessage,
  context: TaskWebSocketLogContext
): TaskLog | null {
  if (message.type === 'task_log' && message.log) {
    return {
      id: context.id,
      task_id: context.taskId,
      level: normalizeTaskLogLevel(message.level),
      message: message.log,
      timestamp: context.timestamp
    }
  }

  if (message.type === 'task_error' && message.error) {
    return {
      id: context.id,
      task_id: context.taskId,
      level: 'error',
      message: message.error,
      timestamp: context.timestamp
    }
  }

  return null
}

export function shouldRefreshTaskAfterWebSocketMessage(message: WSMessage): boolean {
  if (message.type === 'task_complete' || message.type === 'task_error') {
    return true
  }

  return message.type === 'task_status' && isHistoryTask({ status: normalizeTaskStatus(message.status) })
}

function resolveTaskProgressPercent(message: WSMessage): number {
  if (typeof message.progress_percent === 'number') {
    return message.progress_percent
  }

  return Math.round((message.progress ?? 0) * 100)
}

function normalizeTaskLogLevel(level?: string): TaskLog['level'] {
  const normalized = level?.toLowerCase()
  if (normalized === 'warning' || normalized === 'error') {
    return normalized
  }

  return 'info'
}
