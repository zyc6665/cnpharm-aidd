/**
 * 管理员审计日志相关类型（P-38）。
 *
 * 动作、资源类型、结果值均由后端 facets 接口下发，前端不硬编码枚举。
 */

/** 一条审计日志记录。 */
export interface AuditLogRow {
  id: string
  actor: string
  action: string
  result: string
  resource_type: string
  resource_id: string | null
  resource_name: string | null
  detail: Record<string, unknown> | null
  ip: string | null
  request_id: string | null
  created_at: string
}

/** GET /api/v1/admin/audit-logs/facets 的返回体。 */
export interface AuditFacets {
  actors: string[]
  actions: string[]
  resultValues: string[]
  resourceTypes: string[]
}
