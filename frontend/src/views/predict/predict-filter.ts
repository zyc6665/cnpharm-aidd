import type { CsvPreviewRow } from '@/domain/tasks/csv-result'

export interface PredictFilterState {
  /** SMILES 关键词；仅在结果表确有 SMILES 列时生效。 */
  searchText?: string
  hasSmilesColumn?: boolean
  /** 亲和力结果使用「预测亲和力 ≥」单条件筛选。 */
  isAffinityResult?: boolean
  affinityColumnKey?: string
  affinityMin?: number | null
  /** 其他结果按某个数值列 + 可选上下限筛选。 */
  column?: string
  min?: number | null
  max?: number | null
}

/**
 * 结果表筛选。规则：
 * - 未选择筛选列时，上下限不生效（避免「填了最小值但没选列却静默全量」）。
 * - 亲和力结果只按预测亲和力下限过滤，忽略通用列筛选。
 * - SMILES 搜索只对含 SMILES 列的结果生效。
 */
function finiteCell(value: unknown): number | null {
  const raw = String(value ?? '').trim()
  if (!raw) return null
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
}

export function filterPredictRows(rows: CsvPreviewRow[], state: PredictFilterState): CsvPreviewRow[] {
  const keyword = (state.searchText ?? '').trim().toLowerCase()
  return rows.filter(row => {
    if (keyword && state.hasSmilesColumn && !String(row.smiles ?? '').toLowerCase().includes(keyword)) {
      return false
    }
    if (state.isAffinityResult) {
      if (state.affinityMin === null || state.affinityMin === undefined) {
        return true
      }
      const value = finiteCell(row[state.affinityColumnKey ?? ''])
      return value !== null && value >= state.affinityMin
    }
    if (!state.column) {
      return true
    }
    const value = finiteCell(row[state.column])
    if (state.min !== null && state.min !== undefined) {
      if (value === null || value < state.min) {
        return false
      }
    }
    if (state.max !== null && state.max !== undefined) {
      if (value === null || value > state.max) {
        return false
      }
    }
    return true
  })
}
