import type { Task } from '@/types/models'
import { EMPTY_DISPLAY } from '@/domain/common/format'

export type TaskOutputFile = NonNullable<Task['output_files']>[number]

export type TaskScientificAttachmentKey =
  | 'model_card_ref'
  | 'verification_record_ref'
  | 'evidence_level'

export interface TaskScientificAttachmentEntry {
  key: TaskScientificAttachmentKey
  labelKey: string
  value: string
}

const SCIENTIFIC_ATTACHMENT_KEYS: Array<{
  key: TaskScientificAttachmentKey
  labelKey: string
}> = [
  { key: 'model_card_ref', labelKey: 'tasks.scientificModelCard' },
  { key: 'verification_record_ref', labelKey: 'tasks.scientificVerificationRecord' },
  { key: 'evidence_level', labelKey: 'tasks.scientificEvidenceLevel' },
]

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function asStandardResult(value: unknown): Record<string, unknown> | null {
  if (!isRecord(value) || value.result_version !== 'aidd.sciminer/result') {
    return null
  }

  return value
}

function getStandardResult(source: unknown): Record<string, unknown> | null {
  if (!isRecord(source)) {
    return null
  }

  const direct = asStandardResult(source)
  if (direct) {
    return direct
  }

  const wrapped = asStandardResult(source.standard_result)
  if (wrapped) {
    return wrapped
  }

  const nested = source.result
  const nestedDirect = asStandardResult(nested)
  if (nestedDirect) {
    return nestedDirect
  }

  if (isRecord(nested)) {
    return asStandardResult(nested.standard_result)
  }

  return null
}

function getStandardResultMetadataRecords(source: unknown): Record<string, unknown>[] {
  const standardResult = getStandardResult(source)
  if (!standardResult || !isRecord(standardResult.artifacts)) {
    return []
  }

  return Object.values(standardResult.artifacts).flatMap(artifact => {
    if (!isRecord(artifact) || !isRecord(artifact.metadata)) {
      return []
    }

    return [artifact.metadata]
  })
}

function pickScientificAttachmentValue(
  records: Record<string, unknown>[],
  key: TaskScientificAttachmentKey
): string | null {
  for (const record of records) {
    const value = record[key]
    if (typeof value === 'string' && value.trim()) {
      return value
    }
  }

  return null
}

export function getTaskOutputDataEntries(outputData: unknown): [string, unknown][] {
  if (!outputData || typeof outputData !== 'object' || Array.isArray(outputData)) {
    return []
  }

  return Object.entries(outputData as Record<string, unknown>)
}

export function getTaskOutputFiles(task: Pick<Task, 'output_files'>): TaskOutputFile[] {
  return task.output_files ?? []
}

export function getTaskScientificAttachmentEntries(
  ...sources: unknown[]
): TaskScientificAttachmentEntry[] {
  const metadataRecords = sources.flatMap(getStandardResultMetadataRecords)

  return SCIENTIFIC_ATTACHMENT_KEYS.flatMap(({ key, labelKey }) => {
    const value = pickScientificAttachmentValue(metadataRecords, key)

    return value ? [{ key, labelKey, value }] : []
  })
}

export function hasTaskOutputSummaryContent(
  outputData: unknown,
  outputFiles: TaskOutputFile[] = []
): boolean {
  return getTaskOutputDataEntries(outputData).length > 0 || outputFiles.length > 0
}

// ---------------------------------------------------------------------------
// 产物 / 指标概览
//
// 任务详情的「输出结果」原先直接把 output_data 整棵树铺出来，一个真模型任务
// （Boltz-2 亲和力）会得到 2500px 的 JSON，里面 90% 是 artifacts 的文件级清单
// （path / sha256 / content_type）。真正决定「这次跑得怎么样」的只有十几个标量。
// 这里把它压成两块：关键指标 + 产物清单，原始 JSON 收进折叠面板备用。
// ---------------------------------------------------------------------------

export interface OutputMetricSummary {
  key: string
  value: string
}

export interface OutputArtifactSummary {
  key: string
  name: string
  type: string
  fileCount: number
  primaryFile: string | null
}

export interface OutputOverview {
  metrics: OutputMetricSummary[]
  artifacts: OutputArtifactSummary[]
}

function formatMetricValue(value: unknown): string {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)))
  }
  if (typeof value === 'boolean') {
    return value ? '是' : '否'
  }
  if (value === null || value === undefined) {
    return EMPTY_DISPLAY
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

function firstFileName(files: unknown): string | null {
  const candidates: unknown[] = Array.isArray(files)
    ? files
    : isRecord(files)
      ? Object.values(files)
      : []

  for (const candidate of candidates) {
    if (!isRecord(candidate)) {
      continue
    }
    for (const key of ['relative_path', 'filename', 'name', 'path']) {
      const value = candidate[key]
      if (typeof value === 'string' && value.trim()) {
        return value
      }
    }
  }

  return null
}

function countFiles(files: unknown): number {
  if (Array.isArray(files)) {
    return files.length
  }
  if (isRecord(files)) {
    return Object.keys(files).length
  }
  return 0
}

/** 从 output_data（标准 result 或旧式输出）里提取「关键指标 + 产物清单」。 */
export function buildOutputOverview(outputData: unknown): OutputOverview {
  const standardResult = getStandardResult(outputData) ?? (isRecord(outputData) ? outputData : null)
  if (!standardResult) {
    return { metrics: [], artifacts: [] }
  }

  const metrics: OutputMetricSummary[] = []
  for (const bucketKey of ['metrics', 'summary']) {
    const bucket = standardResult[bucketKey]
    if (!isRecord(bucket)) {
      continue
    }
    for (const [key, value] of Object.entries(bucket)) {
      if (value !== null && typeof value === 'object') {
        continue
      }
      if (metrics.some((metric) => metric.key === key)) {
        continue
      }
      metrics.push({ key, value: formatMetricValue(value) })
    }
  }

  const artifacts: OutputArtifactSummary[] = []
  const artifactBucket = standardResult.artifacts
  if (isRecord(artifactBucket)) {
    for (const [key, raw] of Object.entries(artifactBucket)) {
      if (!isRecord(raw)) {
        continue
      }
      const metadata = isRecord(raw.metadata) ? raw.metadata : {}
      const explicitName =
        (typeof metadata.name === 'string' && metadata.name.trim()) ||
        (typeof raw.name === 'string' && raw.name.trim()) ||
        ''
      // 没有可读名时把键名（`affinity_table`）转成「Affinity table」，
      // 直接把键摆在表格里等于没翻译。
      const name = explicitName || key.replace(/[_-]+/g, ' ').replace(/^./, (c) => c.toUpperCase())
      const type =
        (typeof raw.type === 'string' && raw.type) ||
        (typeof raw.semantic_type === 'string' && raw.semantic_type) ||
        EMPTY_DISPLAY
      artifacts.push({
        key,
        name,
        type,
        fileCount: countFiles(raw.files),
        primaryFile: firstFileName(raw.files),
      })
    }
  }

  return { metrics, artifacts }
}
