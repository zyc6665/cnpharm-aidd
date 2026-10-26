import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { Task } from '@/types/models'
import {
  getTaskProgressColor,
  getTaskProgressStatus,
  getTaskStatusColor,
  getTaskStatusTextKey,
  isExecutingTask,
  isHistoryTask,
  isRunningTask,
  isTerminalTask,
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

test('排队中与已超时有独立配色（docs/03 §3.4 新增两态）', () => {
  assert.equal(getTaskStatusColor('queued'), 'blue')
  assert.equal(getTaskStatusColor('timeout'), 'warning')
})

test('任务状态文案 key 由状态模块统一提供', () => {
  assert.equal(getTaskStatusTextKey('pending'), 'tasks.statusPending')
  assert.equal(getTaskStatusTextKey('running'), 'tasks.statusRunning')
  assert.equal(getTaskStatusTextKey('success'), 'tasks.statusSuccess')
  assert.equal(getTaskStatusTextKey('failure'), 'tasks.statusFailure')
  assert.equal(getTaskStatusTextKey('canceled'), 'tasks.statusCanceled')
})

test('排队中与已超时的文案 key 必须落到 i18n 叶子节点', () => {
  assert.equal(getTaskStatusTextKey('queued'), 'tasks.statusQueued')
  assert.equal(getTaskStatusTextKey('timeout'), 'tasks.statusTimeout')
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

test('超时任务的进度条按异常态呈现', () => {
  assert.equal(getTaskProgressStatus('queued'), 'normal')
  assert.equal(getTaskProgressStatus('timeout'), 'exception')
  assert.equal(getTaskProgressColor('timeout'), '#ff4d4f')
  assert.equal(getTaskProgressColor('queued'), '#52c41a')
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

test('排队中的任务算「进行中」但不算「正在执行」', () => {
  // 任务中心的「进行中」页签是「还没出结果」，排队中的任务必须能看到。
  assert.equal(isRunningTask(task('queued')), true)
  // 但只有 running 才会推进进度、才有实时日志。
  assert.equal(isExecutingTask(task('queued')), false)
  assert.equal(isExecutingTask(task('pending')), false)
  assert.equal(isExecutingTask(task('running')), true)
  assert.equal(isHistoryTask(task('queued')), false)
  assert.equal(isTerminalTask(task('queued')), false)
})

test('超时是终态，归入历史而不是进行中', () => {
  assert.equal(isHistoryTask(task('timeout')), true)
  assert.equal(isTerminalTask(task('timeout')), true)
  assert.equal(isRunningTask(task('timeout')), false)
  assert.equal(isExecutingTask(task('timeout')), false)

  assert.equal(isTerminalTask(task('success')), true)
  assert.equal(isTerminalTask(task('failure')), true)
  assert.equal(isTerminalTask(task('canceled')), true)
  assert.equal(isTerminalTask(task('pending')), false)
  assert.equal(isTerminalTask(task('running')), false)
})

test('任务状态归一化接受大小写并对未知状态回退到 pending', () => {
  assert.equal(normalizeTaskStatus('RUNNING'), 'running')
  assert.equal(normalizeTaskStatus('success'), 'success')
  assert.equal(normalizeTaskStatus('unknown'), 'pending')
  assert.equal(normalizeTaskStatus(undefined), 'pending')
})

test('归一化认得后端新增的 QUEUED / TIMEOUT，未知值仍降级 pending', () => {
  assert.equal(normalizeTaskStatus('QUEUED'), 'queued')
  assert.equal(normalizeTaskStatus('Queued'), 'queued')
  assert.equal(normalizeTaskStatus('TIMEOUT'), 'timeout')
  assert.equal(normalizeTaskStatus('Timeout'), 'timeout')
  // 后端将来再加状态时前端不崩，仍然降级为 pending。
  assert.equal(normalizeTaskStatus('REJECTED'), 'pending')
})
