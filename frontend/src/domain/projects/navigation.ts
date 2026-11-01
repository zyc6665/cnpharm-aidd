export type ProjectWorkspaceNavKey =
  | 'overview'
  | 'targets'
  | 'workflow'
  | 'tasks'
  | 'assets'
  | 'candidates'
  | 'lineage'
  | 'settings'
  | 'results'
  | 'decisions'

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

export function buildProjectAssetsPath(projectId: string): string {
  return `/projects/${projectId}/assets`
}

/**
 * 候选物/候选集已从数据资产 Tab 移出（归 M3 域），但仍需一个可达入口：
 * 项目工作台导航与数据资产页顶部的「候选物」按钮都指向它，避免 CandidateDetail /
 * CandidateSetDetail 变成孤儿页面。
 */
export function buildProjectCandidatesPath(projectId: string): string {
  return `/projects/${projectId}/candidates`
}

export function buildProjectResultsPath(projectId: string): string {
  return `/projects/${projectId}/results`
}

export function buildProjectDecisionsPath(projectId: string): string {
  return `/projects/${projectId}/decisions`
}

export function buildProjectWorkspaceNavItems(projectId: string): ProjectWorkspaceNavItem[] {
  return [
    { key: 'overview', label: '项目总览', to: `/projects/${projectId}` },
    { key: 'targets', label: '靶点与结构', to: buildProjectTargetsPath(projectId) },
    { key: 'workflow', label: 'Workflow', to: buildProjectWorkflowPath(projectId) },
    { key: 'tasks', label: '任务中心', to: buildProjectTaskPath(projectId) },
    { key: 'assets', label: '数据资产', to: buildProjectAssetsPath(projectId) },
    { key: 'candidates', label: '候选物', to: buildProjectCandidatesPath(projectId) },
    { key: 'results', label: '结果中心', to: buildProjectResultsPath(projectId) },
    { key: 'decisions', label: '决策记录', to: buildProjectDecisionsPath(projectId) },
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
