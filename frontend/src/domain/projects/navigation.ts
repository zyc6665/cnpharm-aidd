export type ProjectWorkspaceNavKey =
  | 'overview'
  | 'workflow'
  | 'tasks'
  | 'lineage'
  | 'settings'
  | 'targets'

export interface ProjectWorkspaceNavItem {
  key: ProjectWorkspaceNavKey
  label: string
  to: string
}

export interface ProjectWorkspaceNavLocation {
  currentPath: string
  currentProjectId: string
  queryProjectId?: string
}

export function buildProjectTaskPath(projectId: string): string {
  return `/tasks?project_id=${encodeURIComponent(projectId)}`
}

export function buildProjectWorkflowPath(projectId: string): string {
  return `/projects/${projectId}/workflow`
}

export function buildProjectTargetsPath(projectId: string): string {
  return `/projects/${projectId}/targets`
}

export function buildProjectWorkspaceNavItems(projectId: string): ProjectWorkspaceNavItem[] {
  return [
    { key: 'overview', label: '项目总览', to: `/projects/${projectId}` },
    { key: 'targets', label: '靶点与结构', to: buildProjectTargetsPath(projectId) },
    { key: 'workflow', label: 'Workflow', to: buildProjectWorkflowPath(projectId) },
    { key: 'tasks', label: '任务中心', to: buildProjectTaskPath(projectId) },
    { key: 'lineage', label: 'Artifact 谱系', to: `/projects/${projectId}/lineage` },
    { key: 'settings', label: '项目设置', to: `/projects/${projectId}/settings` }
  ]
}

export function isProjectWorkspaceNavItemActive(
  item: ProjectWorkspaceNavItem,
  location: ProjectWorkspaceNavLocation
): boolean {
  if (item.key === 'tasks') {
    return location.currentPath === '/tasks' && location.queryProjectId === location.currentProjectId
  }

  return location.currentPath === item.to || location.currentPath.startsWith(`${item.to}/`)
}
