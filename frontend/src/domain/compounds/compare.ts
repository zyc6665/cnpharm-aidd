import type { CandidateLocation, ComparisonPropertySource } from '@/types/compounds'
import {
  PROPERTY_COLUMNS,
  formatPropertyValue,
  readPropertyValue,
  type PropertyColumn,
  type PropertyKey
} from './properties'

/** 对比页最多同时对比 6 个候选物（后端 `CandidateCompareRequest` 的约束）。 */
export const MAX_COMPARE_CANDIDATES = 6

export interface ComparisonColumn {
  id: string
  label: string
}

export interface ComparisonRow {
  key: PropertyKey
  labelKey: string
  digits: number
  /** 与 `columns` 对齐的格式化取值。 */
  values: string[]
  /** 与 `columns` 对齐的差异高亮：该列取值不全相同即为 `true`。 */
  highlight: boolean[]
}

export interface ComparisonMatrix {
  columns: ComparisonColumn[]
  rows: ComparisonRow[]
}

function resolveColumnLabel(candidate: ComparisonPropertySource, index: number): string {
  const name = (candidate.name || '').trim()
  if (name) {
    return name
  }

  const code = (candidate.code || '').trim()
  if (code) {
    return code
  }

  return `#${index + 1}`
}

/**
 * 构建对比矩阵：行是 7 项固定性质，列是候选物。
 *
 * 判断粒度是「整行是否不一致；不一致则整行高亮」：`highlight[j]` 在同一行内取值
 * 相同，只要该行存在任一候选物取值与其它不同，整行都标记为差异；全行一致则不
 * 高亮，避免满屏告警色。
 */
export function buildComparisonMatrix(
  candidates: ComparisonPropertySource[]
): ComparisonMatrix {
  const columns: ComparisonColumn[] = candidates.map((candidate, index) => ({
    id: candidate.id,
    label: resolveColumnLabel(candidate, index)
  }))

  const rows: ComparisonRow[] = PROPERTY_COLUMNS.map((column: PropertyColumn) => {
    const values = candidates.map(candidate =>
      formatPropertyValue(column.key, readPropertyValue(candidate, column.key))
    )
    const isDifferent = new Set(values).size > 1

    return {
      key: column.key,
      labelKey: column.labelKey,
      digits: column.digits,
      values,
      highlight: values.map(() => isDifferent)
    }
  })

  return { columns, rows }
}

export interface CandidateLocationSource {
  candidate_type?: string
  peptide_sequence?: string | null
  location?: CandidateLocation | null
}

/**
 * 候选物位置标签：小分子挂在化合物结构上，多肽只有序列。
 *
 * 优先用后端给的 `location`，缺失时回退到 `candidate_type`。
 */
export function candidateLocationLabel(candidate: CandidateLocationSource): string {
  if (candidate.location === 'peptide') {
    return 'candidates.location.peptide'
  }
  if (candidate.location === 'compound') {
    return 'candidates.location.compound'
  }

  if (candidate.candidate_type === 'PEPTIDE') {
    return 'candidates.location.peptide'
  }

  return 'candidates.location.compound'
}

/** 候选物是否已可加入对比集合：超过上限时页面应禁止继续添加。 */
export function canAddToComparison(selectedCount: number, max = MAX_COMPARE_CANDIDATES): boolean {
  return selectedCount < max
}
