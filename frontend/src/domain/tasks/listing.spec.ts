import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { Task } from '@/types/models'
import {
  filterTasksByKeyword,
  filterTasksForTab,
  paginateTasks,
  taskSystemViewForTab,
} from './listing'

function task(id: string, status: Task['status'], overrides: Partial<Task> = {}): Task {
  return {
    id,
    tool_id: 'tool-1',
    status,
    progress: 0,
    created_at: '2026-08-05T00:00:00Z',
    ...overrides
  }
}

const tasks: Task[] = [
  task('task-pending', 'pending', { name: 'Docking preparation' }),
  task('task-running', 'running', { tool_name: 'MolP-PC' }),
  task('task-success', 'success', { tool: { name: 'Pocket Finder' } as Task['tool'] }),
  task('task-failure', 'failure'),
  task('task-canceled', 'canceled')
]

test('任务列表按标签页过滤运行中和历史任务', () => {
  assert.deepEqual(
    filterTasksForTab(tasks, 'running').map(item => item.id),
    ['task-pending', 'task-running']
  )
  assert.deepEqual(
    filterTasksForTab(tasks, 'history').map(item => item.id),
    ['task-success', 'task-failure', 'task-canceled']
  )
  assert.deepEqual(
    filterTasksForTab(tasks, 'all').map(item => item.id),
    tasks.map(item => item.id)
  )
})

test('任务列表标签页映射到后端系统视图', () => {
  assert.equal(taskSystemViewForTab('all'), 'all')
  assert.equal(taskSystemViewForTab('running'), 'running')
  assert.equal(taskSystemViewForTab('history'), 'history')
})

test('任务列表关键字过滤覆盖名称、工具名和任务 ID', () => {
  assert.deepEqual(
    filterTasksByKeyword(tasks, 'dock').map(item => item.id),
    ['task-pending']
  )
  assert.deepEqual(
    filterTasksByKeyword(tasks, 'molp').map(item => item.id),
    ['task-running']
  )
  assert.deepEqual(
    filterTasksByKeyword(tasks, 'pocket').map(item => item.id),
    ['task-success']
  )
  assert.deepEqual(
    filterTasksByKeyword(tasks, 'failure').map(item => item.id),
    ['task-failure']
  )
  assert.deepEqual(filterTasksByKeyword(tasks, '   ').length, tasks.length)
})

test('任务列表分页只返回当前页数据', () => {
  assert.deepEqual(
    paginateTasks(tasks, 2, 2).map(item => item.id),
    ['task-success', 'task-failure']
  )
})
