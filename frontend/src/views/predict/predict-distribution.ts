import type { CsvPreviewColumn } from '@/domain/tasks/csv-result'
import type { PredictDetailMetricDef, PredictDetailProfile } from './predictDetailProfiles'

export interface PredictDistributionMetricGroup {
  titleKey: string
  columns: CsvPreviewColumn[]
}

function normalize(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, '')
}

function columnForDef(def: PredictDetailMetricDef, index: Map<string, CsvPreviewColumn>): CsvPreviewColumn | undefined {
  return def.aliases
    .map(alias => index.get(normalize(alias)))
    .find(Boolean)
}

/**
 * 按模型能力族把分布指标分组（吸收/分布/代谢/排泄/毒性等）。
 * 同一能力族的不同模型共用同一份分组；未归类的列放到「其他指标」。
 */
export function buildPredictDistributionGroups(
  profile: PredictDetailProfile,
  columns: CsvPreviewColumn[]
): PredictDistributionMetricGroup[] {
  const index = new Map<string, CsvPreviewColumn>()
  for (const column of columns) {
    index.set(normalize(column.key), column)
    if (column.originalKey) {
      index.set(normalize(column.originalKey), column)
    }
  }

  const allowed = new Set(columns.map(column => column.key))
  const used = new Set<string>()
  const groups: PredictDistributionMetricGroup[] = []

  for (const section of [profile.basic, ...profile.sections].filter(Boolean)) {
    const matched: CsvPreviewColumn[] = []
    for (const def of section!.defs) {
      const column = columnForDef(def, index)
      if (!column || !allowed.has(column.key) || used.has(column.key)) {
        continue
      }
      used.add(column.key)
      matched.push(column)
    }
    if (matched.length) {
      groups.push({ titleKey: section!.titleKey, columns: matched })
    }
  }

  const remaining = columns.filter(column => !used.has(column.key))
  if (remaining.length) {
    groups.push({
      titleKey: groups.length ? 'predict.result.distributionOther' : 'predict.result.distributionAll',
      columns: remaining
    })
  }

  return groups
}
