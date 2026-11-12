/**
 * 「切换项目」时应该落到哪里。
 *
 * 用户在某页面里换项目，期望留在同一个界面上看另一个项目的数据，而不是被弹回工作台。
 * 三种上下文分别处理：
 * 1. 路由路径里带 `:projectId`（`/projects/:projectId/targets` 这类）→ 同名路由换参数；
 * 2. 用查询参数携带项目（`/tasks?project_id=…`、`/design?project_id=…`）→ 同一个 path 换查询参数；
 * 3. 两者都没有 → 没有「同一个界面」可言，落到该项目总览。
 */

export interface ProjectSwitchLocation {
  name?: string | null
  path: string
  params: Record<string, unknown>
  query: Record<string, unknown>
}

export interface ProjectSwitchTarget {
  name?: string
  path?: string
  params?: Record<string, unknown>
  query?: Record<string, unknown>
}

export function resolveProjectSwitchTarget(
  location: ProjectSwitchLocation,
  projectId: string
): ProjectSwitchTarget {
  const routeProjectId = location.params.projectId

  if (typeof routeProjectId === 'string' && routeProjectId.length > 0 && location.name) {
    return {
      name: location.name,
      params: { ...location.params, projectId },
      query: location.query
    }
  }

  const queryProjectId = location.query.project_id
  if (typeof queryProjectId === 'string' && queryProjectId.length > 0) {
    return {
      path: location.path,
      query: { ...location.query, project_id: projectId }
    }
  }

  return { path: `/projects/${encodeURIComponent(projectId)}` }
}

/** 当前路由属于哪个项目：路径参数优先，其次查询参数。 */
export function resolveActiveProjectId(
  params: Record<string, unknown>,
  query: Record<string, unknown>
): string {
  const fromPath = params.projectId
  if (typeof fromPath === 'string' && fromPath.length > 0) return fromPath

  const fromQuery = query.project_id
  if (typeof fromQuery === 'string' && fromQuery.length > 0) return fromQuery

  return ''
}
