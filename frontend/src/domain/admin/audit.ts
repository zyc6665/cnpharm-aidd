/**
 * 审计日志展示逻辑（P-38）。
 *
 * 动作、资源类型、结果值一律来自后端 facets，此模块不维护动作清单。
 */
import type { AuditFacets, AuditLogRow } from '@/types/audit'

/**
 * 时间戳格式化统一复用 `system-health.ts` 的实现，避免同一仓库出现两套日期口径。
 * 这里保留 `formatAuditTimestamp` 名字作为审计域的对外别名（仅转发，无第二份实现）。
 */
export { formatAdminDateTime as formatAuditTimestamp } from './system-health'

/** 前端 page_size 上限，比后端（200）更严，避免一次拉取过多行。 */
export const MAX_AUDIT_PAGE_SIZE = 100

/** 默认每页条数。 */
export const DEFAULT_AUDIT_PAGE_SIZE = 50

/**
 * 破坏性动作词根（小写）：动作名以这些词结尾时，语义上既成事实、只能追加记录。
 * 注意这里只是后缀判定，**不是**动作清单——
 * 动作下拉的可选值全部来自后端 facets。
 */
const IRREVERSIBLE_SUFFIXES = ['delete', 'remove', 'revoke', 'reset', 'purge', 'destroy']

/** 审计筛选条件（组件内状态，允许为空串/空值）。 */
export interface AuditFilters {
  actor?: string
  action?: string
  result?: string
  resource_type?: string
  resource_id?: string
  request_id?: string
  start_time?: string
  end_time?: string
  page?: number
  page_size?: number
}

/** 后端查询参数：只保留有值的键。 */
export interface AuditQueryParams {
  actor?: string
  action?: string
  result?: string
  resource_type?: string
  resource_id?: string
  request_id?: string
  start_time?: string
  end_time?: string
  page: number
  page_size: number
}

/** 审计对象：`resource_type/resource_id`，缺 id 时只显示类型。 */
export function describeAuditTarget(
  row: Pick<AuditLogRow, 'resource_type' | 'resource_id'>
): string {
  const resourceType = (row.resource_type || '').trim()
  const resourceId = (row.resource_id || '').trim()

  if (resourceType && resourceId) {
    return `${resourceType}/${resourceId}`
  }
  return resourceType || resourceId || '-'
}

/** 该动作是否属于不可回滚的破坏性动作（表格中加「只追加」提示）。 */
export function isImmutableAction(action?: string | null): boolean {
  const normalized = (action || '').trim().toLowerCase()
  if (!normalized) {
    return false
  }

  const segments = normalized.split(/[.:/\s_-]+/).filter(Boolean)
  const lastSegment = segments.length > 0 ? String(segments[segments.length - 1]) : normalized
  return IRREVERSIBLE_SUFFIXES.includes(lastSegment)
}

/** 动作下拉选项：直接映射后端 facet，不硬编码。 */
export function buildAuditActionOptions(facets?: AuditFacets | null): string[] {
  return [...(facets?.actions ?? [])]
}

/** 结果下拉选项：直接映射后端 facet。 */
export function buildAuditResultOptions(facets?: AuditFacets | null): string[] {
  return [...(facets?.resultValues ?? [])]
}

/** 资源类型下拉选项：直接映射后端 facet。 */
export function buildAuditResourceTypeOptions(facets?: AuditFacets | null): string[] {
  return [...(facets?.resourceTypes ?? [])]
}

/** actor 下拉选项：直接映射后端 facet。 */
export function buildAuditActorOptions(facets?: AuditFacets | null): string[] {
  return [...(facets?.actors ?? [])]
}

function clampPageSize(value?: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 1) {
    return DEFAULT_AUDIT_PAGE_SIZE
  }
  return Math.min(Math.floor(value), MAX_AUDIT_PAGE_SIZE)
}

function clampPage(value?: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 1) {
    return 1
  }
  return Math.floor(value)
}

function trimmed(value?: string | null): string | undefined {
  const result = (value ?? '').trim()
  return result === '' ? undefined : result
}

/** 把界面筛选状态收敛成后端查询参数：过滤空值、page/page_size 兜底并封顶。 */
export function buildAuditQueryParams(filters?: AuditFilters | null): AuditQueryParams {
  const source = filters ?? {}
  const params: AuditQueryParams = {
    page: clampPage(source.page),
    page_size: clampPageSize(source.page_size)
  }

  const actor = trimmed(source.actor)
  if (actor) params.actor = actor
  const action = trimmed(source.action)
  if (action) params.action = action
  const result = trimmed(source.result)
  if (result) params.result = result
  const resourceType = trimmed(source.resource_type)
  if (resourceType) params.resource_type = resourceType
  const resourceId = trimmed(source.resource_id)
  if (resourceId) params.resource_id = resourceId
  const requestId = trimmed(source.request_id)
  if (requestId) params.request_id = requestId
  const startTime = trimmed(source.start_time)
  if (startTime) params.start_time = startTime
  const endTime = trimmed(source.end_time)
  if (endTime) params.end_time = endTime

  return params
}
