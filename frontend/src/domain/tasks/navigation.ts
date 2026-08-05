import type { Task } from '@/types/models'

export interface TaskProjectContext {
  currentProjectId?: string
  currentProjectName?: string
}

export function getTaskProjectContextLabel(
  task: Pick<Task, 'project_id'>,
  context: TaskProjectContext
): string {
  if (task.project_id === context.currentProjectId && context.currentProjectName) {
    return `项目：${context.currentProjectName}`
  }

  return `项目：${task.project_id?.slice(0, 8) ?? '-'}`
}

export function getTaskArtifactLineagePath(task: Pick<Task, 'project_id'>): string {
  return task.project_id ? `/projects/${task.project_id}/lineage` : '/workspace'
}
