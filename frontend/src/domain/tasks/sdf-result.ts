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

async function expandSingleSdfEntry(
  entry: VisualizationSceneEntry,
  dependencies: ExpandSdfDependencies = {}
): Promise<ExpandedSdfEntries | null> {
  if (entry.format !== 'sdf') {
    return null
  }

  const text = await (dependencies.fetchText || fetchProtectedFileText)(entry.url)
  const records = splitSdfRecords(text)

  if (records.length <= 1) {
    return null
  }

  const objectUrlApi = dependencies.objectUrl || defaultObjectUrlApi
  const urls: string[] = []
  const entries = records.map((record, index) => {
    const url = objectUrlApi.createObjectURL(
      new Blob([record], { type: 'chemical/x-mdl-sdfile' })
    )
    urls.push(url)

    return {
      ...entry,
      key: `${entry.key}::${index + 1}`,
      label: `${entry.label} #${index + 1}`,
      url,
      sdfRecordIndex: index
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
