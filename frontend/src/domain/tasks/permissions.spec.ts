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

test('被拒任务不可重试、也不可取消，但管理员可把它从历史里删掉', () => {
  const owner: TaskActor = { isAdmin: false, userId: 'user-1' }
  const admin: TaskActor = { isAdmin: true }

  // 不可重试：重试接口不做配额准入，放进来就是绕过配额。
  assert.equal(canRetryTask(task('rejected', { user_id: 'user-1' }), owner), false)
  // 不可取消：它已经是终态，从未入队。
  assert.equal(canCancelTask(task('rejected', { user_id: 'user-1' }), owner), false)
  // 可删除：被拒行留在库里是审计证据，但管理员清理历史时不该被它挡住。
  assert.equal(canDeleteTask(task('rejected'), admin), true)
  assert.equal(canDeleteTask(task('rejected', { user_id: 'user-1' }), owner), false)
})
