import type { PaginatedResponse, TaskLog } from '@/types/models'

export function extractTaskLogs(payload: PaginatedResponse<TaskLog> | TaskLog[] | null | undefined): TaskLog[] {
  const normalizeLog = (log: TaskLog): TaskLog => ({
    ...log,
    level: String(log.level).toLowerCase() as TaskLog['level']
  })

  if (!payload) {
    return []
  }

  if (Array.isArray(payload)) {
    return payload.map(normalizeLog)
  }

  return Array.isArray(payload.items) ? payload.items.map(normalizeLog) : []
}
