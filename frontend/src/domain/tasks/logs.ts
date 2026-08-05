import type { PaginatedResponse, TaskLog } from '@/types/models'

const VALID_LOG_LEVELS = new Set<TaskLog['level']>(['info', 'warning', 'error'])

export function normalizeTaskLogLevel(level: unknown): TaskLog['level'] {
  const normalized = typeof level === 'string' ? level.toLowerCase() : ''
  return VALID_LOG_LEVELS.has(normalized as TaskLog['level'])
    ? (normalized as TaskLog['level'])
    : 'info'
}

export function extractTaskLogs(payload: PaginatedResponse<TaskLog> | TaskLog[] | null | undefined): TaskLog[] {
  const normalizeLog = (log: TaskLog): TaskLog => ({
    ...log,
    level: normalizeTaskLogLevel(log.level)
  })

  if (!payload) {
    return []
  }

  if (Array.isArray(payload)) {
    return payload.map(normalizeLog)
  }

  return Array.isArray(payload.items) ? payload.items.map(normalizeLog) : []
}
