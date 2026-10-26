import type { Task } from '@/types/models'
import type { ProjectRole } from '@/types/projects'

export interface TaskActor {
  isAdmin: boolean
  userId?: string
  currentProjectId?: string
  projectRole?: ProjectRole
}

const projectOperatorRoles: ProjectRole[] = ['owner', 'editor', 'runner']
// 与后端 api/v1/tasks.py 的守卫保持一致：超时与失败/取消一样可以重试，
// 排队中（queued）与待调度（pending）、运行中一样可以取消。
const retryableStatuses: Task['status'][] = ['failure', 'timeout', 'canceled']
const cancellableStatuses: Task['status'][] = ['running', 'queued', 'pending']
const deletableStatuses: Task['status'][] = ['success', 'failure', 'timeout', 'canceled']

export function canOperateProjectTask(task: Task, actor: TaskActor): boolean {
  if (!task.project_id || task.project_id !== actor.currentProjectId) return false
  return projectOperatorRoles.includes(actor.projectRole ?? 'viewer')
}

export function canOperateTask(task: Task, actor: TaskActor): boolean {
  if (actor.isAdmin) return true
  if (task.user_id && task.user_id === actor.userId) return true
  return canOperateProjectTask(task, actor)
}

export function canCancelTask(task: Task, actor: TaskActor): boolean {
  return cancellableStatuses.includes(task.status) && canOperateTask(task, actor)
}

export function canRetryTask(task: Task, actor: TaskActor): boolean {
  return retryableStatuses.includes(task.status) && canOperateTask(task, actor)
}

export function canDeleteTask(task: Task, actor: TaskActor): boolean {
  return actor.isAdmin && deletableStatuses.includes(task.status)
}
