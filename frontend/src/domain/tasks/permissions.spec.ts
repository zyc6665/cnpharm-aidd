import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { Task } from '@/types/models'
import {
  canCancelTask,
  canDeleteTask,
  canOperateTask,
  canRetryTask,
  type TaskActor
} from './permissions'

function task(status: Task['status'], overrides: Partial<Task> = {}): Task {
  return {
    id: `task-${status}`,
    tool_id: 'tool-1',
    status,
    progress: 0,
    created_at: '2026-08-05T00:00:00Z',
    ...overrides
  }
}

test('管理员和任务所有者可以操作任务', () => {
  const ownedTask = task('running', { user_id: 'user-1' })

  assert.equal(canOperateTask(ownedTask, { isAdmin: true }), true)
  assert.equal(canOperateTask(ownedTask, { isAdmin: false, userId: 'user-1' }), true)
  assert.equal(canOperateTask(ownedTask, { isAdmin: false, userId: 'user-2' }), false)
})

test('项目 owner editor runner 可以操作项目任务，viewer 不能操作', () => {
  const projectTask = task('running', { project_id: 'project-1' })

  const actor = (projectRole: TaskActor['projectRole']): TaskActor => ({
    isAdmin: false,
    userId: 'user-2',
    currentProjectId: 'project-1',
    projectRole
  })

  assert.equal(canOperateTask(projectTask, actor('owner')), true)
  assert.equal(canOperateTask(projectTask, actor('editor')), true)
  assert.equal(canOperateTask(projectTask, actor('runner')), true)
  assert.equal(canOperateTask(projectTask, actor('viewer')), false)
  assert.equal(
    canOperateTask(projectTask, { ...actor('owner'), currentProjectId: 'project-2' }),
    false
  )
})

test('取消、重试、删除权限由状态和操作者共同决定', () => {
  const owner: TaskActor = { isAdmin: false, userId: 'user-1' }
  const admin: TaskActor = { isAdmin: true }

  assert.equal(canCancelTask(task('pending', { user_id: 'user-1' }), owner), true)
  assert.equal(canCancelTask(task('running', { user_id: 'user-1' }), owner), true)
  assert.equal(canCancelTask(task('success', { user_id: 'user-1' }), owner), false)

  assert.equal(canRetryTask(task('failure', { user_id: 'user-1' }), owner), true)
  assert.equal(canRetryTask(task('canceled', { user_id: 'user-1' }), owner), true)
  assert.equal(canRetryTask(task('running', { user_id: 'user-1' }), owner), false)

  assert.equal(canDeleteTask(task('success'), admin), true)
  assert.equal(canDeleteTask(task('failure'), admin), true)
  assert.equal(canDeleteTask(task('canceled'), admin), true)
  assert.equal(canDeleteTask(task('running'), admin), false)
  assert.equal(canDeleteTask(task('success', { user_id: 'user-1' }), owner), false)
})
