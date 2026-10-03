import type { VisualizationSceneEntry } from './result-visualization'
import { fetchProtectedFileText } from '../../utils/protected-file-access.ts'

interface ObjectUrlApi {
  createObjectURL(blob: Blob): string
  revokeObjectURL(url: string): void
}

interface ExpandSdfDependencies {
  fetchText?: (url: string) => Promise<string>
  objectUrl?: ObjectUrlApi
}

interface ExpandedSdfEntries {
  entries: VisualizationSceneEntry[]
  revoke: () => void
}

export interface SdfObjectUrlResource {
  url: string
  revoke: () => void
}

const defaultObjectUrlApi: ObjectUrlApi = {
  createObjectURL(blob) {
    return URL.createObjectURL(blob)
  },
  revokeObjectURL(url) {
    URL.revokeObjectURL(url)
  }
}

function withTrailingNewline(record: string): string {
  return record.endsWith('\n') ? record : `${record}\n`
}

function isMolfileCountsLine(line: string): boolean {
  return /^\s*\d{1,3}\s+\d{1,3}\s+.+\bV(?:2000|3000)\b/.test(line)
}

export function normalizeSdfRecord(record: string): string {
  const normalized = withTrailingNewline(record.replace(/\r\n/g, '\n').replace(/\r/g, '\n'))
  const lines = normalized.split('\n')
  const countsIndex = lines.findIndex(isMolfileCountsLine)

  if (countsIndex < 0 || countsIndex >= 3) {
    return normalized
  }

  lines.splice(countsIndex, 0, ...Array.from({ length: 3 - countsIndex }, () => ''))
  return lines.join('\n')
}

export function splitSdfRecords(text: string): string[] {
  const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const records = normalized.match(/[\s\S]*?\${4}(?:\n|$)/g) || []

  if (records.length > 0) {
    return records
      .filter(record => record.replace(/\${4}(?:\n|$)/g, '').trim().length > 0)
      .map(withTrailingNewline)
  }

  return normalized.trim().length > 0 ? [withTrailingNewline(normalized)] : []
}

export function normalizeSdfText(text: string): string {
  return splitSdfRecords(text)
    .map(normalizeSdfRecord)
    .join('')
}

async function fetchSdfText(
  fileUrl: string,
  dependencies: ExpandSdfDependencies
): Promise<string> {
  if (dependencies.fetchText) {
    return await dependencies.fetchText(fileUrl)
  }

  if (fileUrl.startsWith('blob:') || fileUrl.startsWith('data:')) {
    const response = await fetch(fileUrl)
    if (!response.ok) {
      throw new Error(`读取 SDF 文件失败：${response.status}`)
    }
    return await response.text()
  }

  return await fetchProtectedFileText(fileUrl)
}

export async function createNormalizedSdfObjectUrl(
  fileUrl: string,
  dependencies: ExpandSdfDependencies = {}
): Promise<SdfObjectUrlResource> {
  const text = await fetchSdfText(fileUrl, dependencies)
  const objectUrlApi = dependencies.objectUrl || defaultObjectUrlApi
  const objectUrl = objectUrlApi.createObjectURL(
    new Blob([normalizeSdfText(text)], { type: 'chemical/x-mdl-sdfile' })
  )

  return {
    url: objectUrl,
    revoke: () => objectUrlApi.revokeObjectURL(objectUrl)
  }
}

async function expandSingleSdfEntry(
  entry: VisualizationSceneEntry,
  dependencies: ExpandSdfDependencies = {}
): Promise<ExpandedSdfEntries | null> {
  if (entry.format !== 'sdf') {
    return null
  }

  const text = await (dependencies.fetchText || fetchProtectedFileText)(entry.url)
  const records = splitSdfRecords(text)
  const normalizedRecords = records.map(normalizeSdfRecord)
  const hasNormalizedRecord = normalizedRecords.some((record, index) => record !== records[index])

  if (records.length <= 1 && !hasNormalizedRecord) {
    return null
  }

  const objectUrlApi = dependencies.objectUrl || defaultObjectUrlApi
  const urls: string[] = []
  const isMultiRecord = normalizedRecords.length > 1
  const entries = normalizedRecords.map((record, index) => {
    const url = objectUrlApi.createObjectURL(
      new Blob([record], { type: 'chemical/x-mdl-sdfile' })
    )
    urls.push(url)

    return {
      ...entry,
      ...(isMultiRecord
        ? {
            key: `${entry.key}::${index + 1}`,
            label: `${entry.label} #${index + 1}`,
            sdfRecordIndex: index
          }
        : {}),
      url,
    }
  })

  return {
    entries,
    revoke: () => {
      urls.forEach(url => objectUrlApi.revokeObjectURL(url))
    }
  }
}

export async function expandSdfOutputEntries(
  entries: VisualizationSceneEntry[],
  dependencies: ExpandSdfDependencies = {}
): Promise<ExpandedSdfEntries> {
  const revokeCallbacks: Array<() => void> = []
  const expandedEntries: VisualizationSceneEntry[] = []

  for (const entry of entries) {
    const expanded = await expandSingleSdfEntry(entry, dependencies)
    if (expanded) {
      expandedEntries.push(...expanded.entries)
      revokeCallbacks.push(expanded.revoke)
      continue
    }

    expandedEntries.push(entry)
  }

  return {
    entries: expandedEntries,
    revoke: () => {
      revokeCallbacks.forEach(revoke => revoke())
    }
  }
}
