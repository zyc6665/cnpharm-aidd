import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { Task } from '@/types/models'
import {
  getTaskProgressColor,
  getTaskProgressStatus,
  getTaskStatusColor,
  getTaskStatusTextKey,
  isHistoryTask,
  isRunningTask,
  normalizeTaskStatus
} from './status'

function task(status: Task['status']): Task {
  return {
    id: `task-${status}`,
    tool_id: 'tool-1',
    status,
    progress: 0,
    created_at: '2026-08-05T00:00:00Z'
  }
}

test('任务状态展示规则保持与任务中心一致', () => {
  assert.equal(getTaskStatusColor('pending'), 'orange')
  assert.equal(getTaskStatusColor('running'), 'processing')
  assert.equal(getTaskStatusColor('success'), 'success')
  assert.equal(getTaskStatusColor('failure'), 'error')
  assert.equal(getTaskStatusColor('canceled'), 'default')
})

test('任务状态文案 key 由状态模块统一提供', () => {
  assert.equal(getTaskStatusTextKey('pending'), 'tasks.statusPending')
  assert.equal(getTaskStatusTextKey('running'), 'tasks.statusRunning')
  assert.equal(getTaskStatusTextKey('success'), 'tasks.statusSuccess')
  assert.equal(getTaskStatusTextKey('failure'), 'tasks.statusFailure')
  assert.equal(getTaskStatusTextKey('canceled'), 'tasks.statusCanceled')
})

test('任务进度条状态和颜色由任务状态决定', () => {
  assert.equal(getTaskProgressStatus('running'), 'active')
  assert.equal(getTaskProgressStatus('failure'), 'exception')
  assert.equal(getTaskProgressStatus('success'), 'success')
  assert.equal(getTaskProgressStatus('pending'), 'normal')

  assert.equal(getTaskProgressColor('running'), '#1890ff')
  assert.equal(getTaskProgressColor('failure'), '#ff4d4f')
  assert.equal(getTaskProgressColor('success'), '#52c41a')
})

test('运行中和历史任务分类保持互斥', () => {
  assert.equal(isRunningTask(task('pending')), true)
  assert.equal(isRunningTask(task('running')), true)
  assert.equal(isRunningTask(task('success')), false)

  assert.equal(isHistoryTask(task('success')), true)
  assert.equal(isHistoryTask(task('failure')), true)
  assert.equal(isHistoryTask(task('canceled')), true)
  assert.equal(isHistoryTask(task('running')), false)
})

test('任务状态归一化接受大小写并对未知状态回退到 pending', () => {
  assert.equal(normalizeTaskStatus('RUNNING'), 'running')
  assert.equal(normalizeTaskStatus('success'), 'success')
  assert.equal(normalizeTaskStatus('unknown'), 'pending')
  assert.equal(normalizeTaskStatus(undefined), 'pending')
})
