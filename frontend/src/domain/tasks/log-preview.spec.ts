import { describe, expect, it } from 'vitest'
import type { TaskLog } from '@/types/models'
import {
  formatTaskLogPreviewTime,
  getHiddenTaskLogCount,
  getTaskLogPreviewColor,
  getVisibleTaskLogs,
} from './log-preview'

function log(overrides: Partial<TaskLog> = {}): TaskLog {
  return {
    id: 1,
    task_id: 'task-1',
    level: 'info',
    message: 'running',
    timestamp: '2026-08-05T06:00:01.234Z',
    ...overrides,
  }
}

describe('task log preview display rules', () => {
  it('formats timestamps for compact log preview rows', () => {
    expect(formatTaskLogPreviewTime('2026-08-05T06:00:01.234Z')).toMatch(
      /^\d{2}:\d{2}:\d{2}\.\d{3}$/
    )
  })

  it('maps normalized log levels to tag colors', () => {
    expect(getTaskLogPreviewColor('info')).toBe('blue')
    expect(getTaskLogPreviewColor('warning')).toBe('orange')
    expect(getTaskLogPreviewColor('error')).toBe('red')
    expect(getTaskLogPreviewColor('debug')).toBe('default')
  })

  it('limits visible logs and reports hidden count', () => {
    const logs = [log({ id: 1 }), log({ id: 2 }), log({ id: 3 })]

    expect(getVisibleTaskLogs(logs, 2).map(item => item.id)).toEqual([1, 2])
    expect(getHiddenTaskLogCount(logs, 2)).toBe(1)
    expect(getVisibleTaskLogs(logs, 0).map(item => item.id)).toEqual([1, 2, 3])
    expect(getHiddenTaskLogCount(logs, 0)).toBe(0)
  })
})
