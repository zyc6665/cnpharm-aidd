/**
 * 管理员审计日志接口（P-38）。
 *
 * 只读：审计日志不可修改、不可删除。
 */
import { get } from '@/api/request'
import type { ApiResponse } from '@/types/api'
import type { AuditFacets, AuditLogRow } from '@/types/audit'
import type { PaginatedResponse } from '@/types/models'

/** 只读查询统一配置：不弹全局错误提示，失败重试一次。 */
const READ_OPTIONS = { silent: true, retry: 1 } as const

/** 审计日志筛选与分页查询参数。 */
export interface AuditLogQuery {
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

/** 分页查询审计日志。 */
export async function listAuditLogs(
  params: AuditLogQuery
): Promise<ApiResponse<PaginatedResponse<AuditLogRow>>> {
  return get<PaginatedResponse<AuditLogRow>, AuditLogQuery>('/admin/audit-logs', params, READ_OPTIONS)
}

/** 筛选可选值（actor / action / result / resource_type），由后端下发。 */
export async function getAuditFacets(): Promise<ApiResponse<AuditFacets>> {
  return get<AuditFacets>('/admin/audit-logs/facets', undefined, READ_OPTIONS)
}
