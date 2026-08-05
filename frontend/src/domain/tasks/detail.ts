import dayjs from 'dayjs'
import type { TaskStatus } from '@/types/models'

export type TaskCompletedTitleKey = 'tasks.completed' | 'tasks.failed' | 'tasks.canceled'

export function getTaskCompletedTitleKey(status: TaskStatus): TaskCompletedTitleKey {
  if (status === 'failure') return 'tasks.failed'
  if (status === 'canceled') return 'tasks.canceled'
  return 'tasks.completed'
}

export function formatTaskDetailTime(time: string): string {
  return dayjs(time).format('YYYY-MM-DD HH:mm:ss')
}

export function formatTaskFileSize(bytes?: number): string {
  if (!bytes || bytes === 0) {
    return '0 B'
  }

  const unit = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(unit)), sizes.length - 1)
  return `${parseFloat((bytes / Math.pow(unit, index)).toFixed(2))} ${sizes[index]}`
}
