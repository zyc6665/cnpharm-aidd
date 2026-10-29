import type { Task } from '@/types/models'

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
