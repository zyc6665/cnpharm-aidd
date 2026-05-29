import test from 'node:test'
import assert from 'node:assert/strict'

import { extractTaskLogs } from '../src/views/tasks/logs.ts'

test('extractTaskLogs 应从分页响应中提取日志列表', () => {
  const logs = extractTaskLogs({
    items: [
      {
        id: 1,
        task_id: 'task-1',
        level: 'INFO',
        message: '任务执行成功',
        timestamp: '2026-05-27T09:00:00Z'
      }
    ],
    total: 1,
    page: 1,
    page_size: 50,
    total_pages: 1
  })

  assert.equal(logs.length, 1)
  assert.equal(logs[0]?.message, '任务执行成功')
  assert.equal(logs[0]?.level, 'info')
})

test('extractTaskLogs 应兼容已是数组的旧数据', () => {
  const logs = extractTaskLogs([
    {
      id: 2,
      task_id: 'task-2',
      level: 'warning',
      message: '任务仍在运行',
      timestamp: '2026-05-27T09:10:00Z'
    }
  ])

  assert.equal(logs.length, 1)
  assert.equal(logs[0]?.level, 'warning')
})
