export type ProjectWorkspaceNavKey =
  | 'overview'
  | 'targets'
  | 'design'
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

/**
 * 项目内的主入口是「设计流程」（引导式五步）；画布编排是它的高级形态，
 * 从设计流程页的「高级」按钮进入，不再单独占一个顶级导航位。
 */
export function buildProjectDesignPath(projectId: string): string {
  return `/design?project_id=${encodeURIComponent(projectId)}`
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
    { key: 'design', label: '设计流程', to: buildProjectDesignPath(projectId) },
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

  if (item.key === 'design') {
    // 设计流程页的地址是 `/design?project_id=…`：路径与查询参数都要对上，
    // 否则任何项目在设计流程页都会亮起来。画布编排是它的高级形态，同一项也亮。
    if (location.currentPath === `/projects/${location.currentProjectId}/workflow`) {
      return true
    }
    return location.currentPath === '/design' && location.queryProjectId === location.currentProjectId
  }

  if (item.key === 'overview') {
    // 项目总览的地址是所有子页的前缀（`/projects/:id`），必须精确匹配，
    // 否则进任何子页都会同时高亮「项目总览」，看起来像两条都被选中。
    return location.currentPath === item.to
  }

  return location.currentPath === item.to || location.currentPath.startsWith(`${item.to}/`)
}
