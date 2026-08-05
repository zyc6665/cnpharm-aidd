import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { WSMessage } from '@/types/models'
import {
  isTaskWebSocketMessageForTask,
  resolveTaskWebSocketLog,
  resolveTaskWebSocketProgressUpdate,
  shouldRefreshTaskAfterWebSocketMessage
} from './websocket'

test('WebSocket 任务消息只处理当前任务 ID', () => {
  assert.equal(isTaskWebSocketMessageForTask({ type: 'task_progress', task_id: 'task-1' }, 'task-1'), true)
  assert.equal(isTaskWebSocketMessageForTask({ type: 'task_progress', task_id: 'task-2' }, 'task-1'), false)
  assert.equal(isTaskWebSocketMessageForTask({ type: 'connected' }, 'task-1'), false)
})

test('WebSocket 进度更新优先使用 progress_percent 并归一化状态', () => {
  const percentUpdate = resolveTaskWebSocketProgressUpdate(
    { type: 'task_progress', task_id: 'task-1', progress_percent: 42, status: 'running' },
    { taskId: 'task-1', currentProgress: 8 }
  )
  assert.deepEqual(percentUpdate, { taskId: 'task-1', progress: 42, status: 'running' })

  const ratioUpdate = resolveTaskWebSocketProgressUpdate(
    { type: 'task_progress', task_id: 'task-1', progress: 0.73 },
    { taskId: 'task-1', currentProgress: 8 }
  )
  assert.deepEqual(ratioUpdate, { taskId: 'task-1', progress: 73, status: undefined })
})

test('WebSocket 终态消息转换为任务进度更新', () => {
  assert.deepEqual(
    resolveTaskWebSocketProgressUpdate(
      { type: 'task_status', task_id: 'task-1', status: 'failure' },
      { taskId: 'task-1', currentProgress: 31 }
    ),
    { taskId: 'task-1', progress: 31, status: 'failure' }
  )
  assert.deepEqual(
    resolveTaskWebSocketProgressUpdate(
      { type: 'task_complete', task_id: 'task-1' },
      { taskId: 'task-1', currentProgress: 31 }
    ),
    { taskId: 'task-1', progress: 100, status: 'success' }
  )
  assert.deepEqual(
    resolveTaskWebSocketProgressUpdate(
      { type: 'task_error', task_id: 'task-1' },
      { taskId: 'task-1', currentProgress: 31 }
    ),
    { taskId: 'task-1', progress: 31, status: 'failure' }
  )
})

test('WebSocket 日志消息生成标准 TaskLog', () => {
  const log = resolveTaskWebSocketLog(
    { type: 'task_log', task_id: 'task-1', log: 'running', level: 'WARNING' },
    { taskId: 'task-1', id: 1, timestamp: '2026-08-05T00:00:00Z' }
  )
  assert.deepEqual(log, {
    id: 1,
    task_id: 'task-1',
    level: 'warning',
    message: 'running',
    timestamp: '2026-08-05T00:00:00Z'
  })

  const error = resolveTaskWebSocketLog(
    { type: 'task_error', task_id: 'task-1', error: 'failed' },
    { taskId: 'task-1', id: 2, timestamp: '2026-08-05T00:01:00Z' }
  )
  assert.equal(error?.level, 'error')
  assert.equal(error?.message, 'failed')
})

test('WebSocket 终态消息触发详情和日志刷新', () => {
  const running: WSMessage = { type: 'task_status', task_id: 'task-1', status: 'running' }
  const failure: WSMessage = { type: 'task_status', task_id: 'task-1', status: 'failure' }

  assert.equal(shouldRefreshTaskAfterWebSocketMessage(running), false)
  assert.equal(shouldRefreshTaskAfterWebSocketMessage(failure), true)
  assert.equal(shouldRefreshTaskAfterWebSocketMessage({ type: 'task_complete', task_id: 'task-1' }), true)
  assert.equal(shouldRefreshTaskAfterWebSocketMessage({ type: 'task_error', task_id: 'task-1' }), true)
})
