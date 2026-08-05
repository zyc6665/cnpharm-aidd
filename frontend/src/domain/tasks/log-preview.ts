import dayjs from 'dayjs'
import type { TaskLog } from '@/types/models'

export function getVisibleTaskLogs(logs: TaskLog[], maxItems?: number): TaskLog[] {
  if (!maxItems || maxItems <= 0) {
    return logs
  }

  return logs.slice(0, maxItems)
}

export function getHiddenTaskLogCount(logs: TaskLog[], maxItems?: number): number {
  if (!maxItems || maxItems <= 0) {
    return 0
  }

  return Math.max(logs.length - maxItems, 0)
}

export function formatTaskLogPreviewTime(time: string): string {
  return dayjs(time).format('HH:mm:ss.SSS')
}

export function getTaskLogPreviewColor(level: string): string {
  const colors: Record<string, string> = {
    info: 'blue',
    warning: 'orange',
    error: 'red',
  }
  return colors[level] || 'default'
}
