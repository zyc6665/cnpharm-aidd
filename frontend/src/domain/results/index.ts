import type { ProjectResultSummary, TraceabilityPackage } from '@/types/compounds'
import type { TaskStatus } from '@/types/models'

/** 结果列表/详情的终态集合（后端只回终态任务）。 */
export const RESULT_STATUSES: readonly TaskStatus[] = ['success', 'failure', 'canceled']

/** 追溯包六个折叠分区，`key` 对应 `TraceabilityPackage` 的顶层字段。 */
export type TraceabilitySectionKey =
  | 'task'
  | 'timeline'
  | 'inputs'
  | 'environment'
  | 'process'
  | 'outputs'

export interface TraceabilitySection {
  key: TraceabilitySectionKey
  labelKey: string
}

export const TRACEABILITY_SECTIONS: readonly TraceabilitySection[] = [
  { key: 'task', labelKey: 'results.traceability.sections.task' },
  { key: 'timeline', labelKey: 'results.traceability.sections.timeline' },
  { key: 'inputs', labelKey: 'results.traceability.sections.inputs' },
  { key: 'environment', labelKey: 'results.traceability.sections.environment' },
  { key: 'process', labelKey: 'results.traceability.sections.process' },
  { key: 'outputs', labelKey: 'results.traceability.sections.outputs' }
]

function toTimestamp(value: string | null | undefined): number | null {
  if (!value) {
    return null
  }

  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed
}

/**
 * 结果按完成时间降序，`finished_at` 为 `null`/`undefined` 的排在最后。
 *
 * 同级保持传入顺序（`Array.prototype.sort` 在 ES2019+ 已是稳定排序），
 * 这样「未完成」分组仍按后端给的 `created_at` 降序展示。
 */
export function sortResultsByFinishedDesc<T extends { finished_at?: string | null }>(
  results: readonly T[]
): T[] {
  return results
    .map((result, index) => ({ result, index, timestamp: toTimestamp(result.finished_at) }))
    .sort((left, right) => {
      if (left.timestamp === null && right.timestamp === null) {
        return left.index - right.index
      }
      if (left.timestamp === null) {
        return 1
      }
      if (right.timestamp === null) {
        return -1
      }
      if (left.timestamp === right.timestamp) {
        return left.index - right.index
      }
      return right.timestamp - left.timestamp
    })
    .map(entry => entry.result)
}

/** 追溯包是否已经导出过（`exportedAt` 有值）。 */
export function isTraceabilityExported(traceability: TraceabilityPackage | null): boolean {
  return Boolean(traceability?.exportedAt)
}

/** 追溯包的输入快照数量与产物数量，用于概要行。 */
export function summarizeTraceability(traceability: TraceabilityPackage | null): {
  inputCount: number
  outputCount: number
  packageVersion: string
} {
  return {
    inputCount: traceability?.inputs?.length ?? 0,
    outputCount: traceability?.outputs?.length ?? 0,
    packageVersion: traceability?.packageVersion ?? ''
  }
}

/** 结果耗时展示：后端给秒，缺失时显示短横线。 */
export function formatExecutionSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return '-'
  }

  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`
  }

  const minutes = Math.floor(seconds / 60)
  const remainder = Math.round(seconds - minutes * 60)
  return `${minutes}m ${remainder}s`
}

export interface ResultSortSource {
  finished_at?: string | null
}

export type { ProjectResultSummary }
