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
  return `/projects/${encodeURIComponent(projectId)}/tasks`
}

export function buildProjectTaskDetailPath(projectId: string, taskId: string): string {
  return `/projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(taskId)}`
}

export function buildProjectTaskResultPath(projectId: string, taskId: string): string {
  return `/projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(taskId)}/result`
}

export function buildProjectResultDetailPath(projectId: string, taskId: string): string {
  return `/projects/${encodeURIComponent(projectId)}/results/${encodeURIComponent(taskId)}`
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

export function buildProjectSettingsPath(projectId: string): string {
  return `/projects/${projectId}/settings`
}

export function buildProjectLineagePath(projectId: string): string {
  return `/projects/${projectId}/lineage`
}

/** 「数据与产物」下的三个视图切换项（数据资产 / 结果中心 / Artifact 谱系）。 */
export function buildProjectDataViewTabs(projectId: string) {
  return [
    { key: 'assets', label: '数据资产', to: buildProjectAssetsPath(projectId) },
    { key: 'results', label: '结果中心', to: buildProjectResultsPath(projectId) },
    { key: 'lineage', label: 'Artifact 谱系', to: buildProjectLineagePath(projectId) },
  ] as const
}

/** 「候选与决策」下的两个视图切换项（候选物 / 决策记录）。 */
export function buildProjectCandidateViewTabs(projectId: string) {
  return [
    { key: 'candidates', label: '候选物', to: buildProjectCandidatesPath(projectId) },
    { key: 'decisions', label: '决策记录', to: buildProjectDecisionsPath(projectId) },
  ] as const
}

/** 「单步工具」下的两个视图切换项（单步工具 / 靶点与结构）。 */
export function buildProjectFlowViewTabs(projectId: string) {
  return [
    { key: 'design', label: '单步工具', to: buildProjectDesignPath(projectId) },
    { key: 'targets', label: '靶点与结构', to: buildProjectTargetsPath(projectId) },
  ] as const
}

/**
 * 项目内横向导航收敛为 6 个主入口 + 1 个右侧设置：
 * - 项目总览：项目阶段、成果看板与最近活动
 * - 单步工具：7 个独立工具与靶点结构（直接选项目数据或本地上传）
 * - 工作流：多步串联画布编排（需要自动化接力时使用）
 * - 任务中心：当前项目的执行记录
 * - 数据与产物：数据空间（Artifact）与资产 / 结果中心 / Artifact 谱系
 * - 候选与决策：候选物与决策记录
 * - 项目设置：右侧齿轮图标
 */
export function buildProjectWorkspaceNavItems(projectId: string): ProjectWorkspaceNavItem[] {
  return [
    { key: 'overview', label: '项目总览', to: `/projects/${projectId}` },
    { key: 'design', label: '单步工具', to: buildProjectDesignPath(projectId) },
    { key: 'workflow', label: '工作流', to: buildProjectWorkflowPath(projectId) },
    { key: 'tasks', label: '任务中心', to: buildProjectTaskPath(projectId) },
    { key: 'assets', label: '数据与产物', to: buildProjectAssetsPath(projectId) },
    { key: 'candidates', label: '候选与决策', to: buildProjectCandidatesPath(projectId) },
    { key: 'settings', label: '项目设置', to: buildProjectSettingsPath(projectId) }
  ]
}

export function isProjectWorkspaceNavItemActive(
  item: ProjectWorkspaceNavItem,
  location: ProjectWorkspaceNavLocation
): boolean {
  const pid = location.currentProjectId

  if (item.key === 'tasks') {
    const prefix = `/projects/${pid}/tasks`
    if (location.currentPath === prefix || location.currentPath.startsWith(`${prefix}/`)) {
      return true
    }
    return location.currentPath === '/tasks' && location.queryProjectId === pid
  }

  if (item.key === 'workflow') {
    const prefix = `/projects/${pid}/workflow`
    return location.currentPath === prefix || location.currentPath.startsWith(`${prefix}/`)
  }

  if (item.key === 'design') {
    // 单步工具覆盖：`/design?project_id=` 与靶点与结构 `/projects/:id/targets`。
    if (
      location.currentPath === `/projects/${pid}/targets` ||
      location.currentPath.startsWith(`/projects/${pid}/targets/`)
    ) {
      return true
    }
    return location.currentPath === '/design' && location.queryProjectId === pid
  }

  if (item.key === 'assets') {
    // 数据与产物合并了数据资产、结果中心、Artifact 谱系三个视图。
    const prefixes = [
      `/projects/${pid}/assets`,
      `/projects/${pid}/results`,
      `/projects/${pid}/lineage`
    ]
    return prefixes.some(
      prefix => location.currentPath === prefix || location.currentPath.startsWith(`${prefix}/`)
    )
  }

  if (item.key === 'candidates') {
    // 候选与决策合并了候选物（含对比）与决策记录两个视图。
    const prefixes = [`/projects/${pid}/candidates`, `/projects/${pid}/decisions`]
    return prefixes.some(
      prefix => location.currentPath === prefix || location.currentPath.startsWith(`${prefix}/`)
    )
  }

  if (item.key === 'overview') {
    // 项目总览的地址是所有子页的前缀（`/projects/:id`），必须精确匹配，
    // 否则进任何子页都会同时高亮「项目总览」，看起来像两条都被选中。
    return location.currentPath === item.to
  }

  return location.currentPath === item.to || location.currentPath.startsWith(`${item.to}/`)
}
