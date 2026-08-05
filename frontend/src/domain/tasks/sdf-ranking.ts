import type { TaskFileReference, VisualizationSceneEntry } from './result-visualization'

import { fetchProtectedFileText } from '../../utils/protected-file-access.ts'

interface ScoreRanking {
  label: 'Score' | 'QED' | 'SA' | 'Vina'
  higherIsBetter: boolean
  scoresByFileKey: Map<string, number>
  scoresByRecordIndex: Map<number, number>
}

interface CsvRow {
  [key: string]: string
}

const SCORE_COLUMNS = [
  { keys: ['composite_score', 'score', 'ranking_score'], label: 'Score' as const, higherIsBetter: true },
  { keys: ['qed'], label: 'QED' as const, higherIsBetter: true },
  { keys: ['sa', 'sa_score', 'synthetic_accessibility'], label: 'SA' as const, higherIsBetter: false },
  { keys: ['vina', 'vina_score', 'docking_score', 'affinity'], label: 'Vina' as const, higherIsBetter: false }
]

const FILE_COLUMNS = ['sdf_file', 'sdf', 'file', 'filename', 'path']
const RECORD_INDEX_COLUMNS = ['index', 'record_index', 'sdf_index']
const TOP_RANKED_SDF_LIMIT = 10

function getFileName(file: TaskFileReference): string {
  return file.original_name || file.filename || file.relative_path || file.url || ''
}

function normalizeHeader(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
}

function parseCsvLine(line: string): string[] {
  const cells: string[] = []
  let cell = ''
  let inQuotes = false

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index]
    const nextChar = line[index + 1]

    if (char === '"' && inQuotes && nextChar === '"') {
      cell += '"'
      index += 1
      continue
    }

    if (char === '"') {
      inQuotes = !inQuotes
      continue
    }

    if (char === ',' && !inQuotes) {
      cells.push(cell)
      cell = ''
      continue
    }

    cell += char
  }

  cells.push(cell)
  return cells.map(value => value.trim())
}

function parseCsvRows(text: string): CsvRow[] {
  const lines = text
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')
    .filter(line => line.trim().length > 0)

  if (lines.length <= 1) {
    return []
  }

  const headers = parseCsvLine(lines[0] || '').map(normalizeHeader)

  return lines.slice(1).map(line => {
    const values = parseCsvLine(line)
    return headers.reduce<CsvRow>((row, header, index) => {
      row[header] = values[index] || ''
      return row
    }, {})
  })
}

function normalizeFileKey(value: string): string {
  return value.trim().replace(/\\/g, '/').replace(/^artifacts\//i, '').toLowerCase()
}

function fileKeyCandidates(value?: string): string[] {
  if (!value) {
    return []
  }

  const normalized = normalizeFileKey(value)
  const pathBaseName = normalized.split('/').pop() || normalized
  const flattenedBaseName = normalized.split('__').pop() || normalized

  return Array.from(new Set([normalized, pathBaseName, flattenedBaseName].filter(Boolean)))
}

function entryFileKeyCandidates(entry: VisualizationSceneEntry): string[] {
  return Array.from(new Set([
    ...fileKeyCandidates(entry.relativePath),
    ...fileKeyCandidates(entry.label),
    ...fileKeyCandidates(entry.url)
  ]))
}

function parseScoreRanking(csvText: string): ScoreRanking | null {
  const rows = parseCsvRows(csvText)
  if (!rows.length) {
    return null
  }

  const headers = new Set(Object.keys(rows[0] || {}))
  const scoreColumn = SCORE_COLUMNS.find(candidate =>
    candidate.keys.some(key => headers.has(key))
  )
  const fileColumn = FILE_COLUMNS.find(key => headers.has(key))
  const recordIndexColumn = RECORD_INDEX_COLUMNS.find(key => headers.has(key))

  if (!scoreColumn || (!fileColumn && !recordIndexColumn)) {
    return null
  }

  const scoreKey = scoreColumn.keys.find(key => headers.has(key))
  if (!scoreKey) {
    return null
  }

  const sortedRows = rows
    .map(row => ({
      fileValue: fileColumn ? row[fileColumn] || '' : '',
      recordIndex: recordIndexColumn ? Number(row[recordIndexColumn]) : Number.NaN,
      score: Number(row[scoreKey])
    }))
    .filter(row => (row.fileValue || Number.isInteger(row.recordIndex)) && Number.isFinite(row.score))
    .sort((left, right) =>
      scoreColumn.higherIsBetter ? right.score - left.score : left.score - right.score
    )

  const scoresByFileKey = new Map<string, number>()
  const scoresByRecordIndex = new Map<number, number>()
  for (const row of sortedRows) {
    for (const candidate of fileKeyCandidates(row.fileValue)) {
      scoresByFileKey.set(candidate, row.score)
    }
    if (Number.isInteger(row.recordIndex)) {
      scoresByRecordIndex.set(row.recordIndex, row.score)
    }
  }

  return scoresByFileKey.size || scoresByRecordIndex.size
    ? {
        label: scoreColumn.label,
        higherIsBetter: scoreColumn.higherIsBetter,
        scoresByFileKey,
        scoresByRecordIndex
      }
    : null
}

export function detectSdfScoreRankingFile(
  file?: TaskFileReference | null
): TaskFileReference | null {
  if (!file?.url) {
    return null
  }

  const lowerName = getFileName(file).toLowerCase()
  if (!lowerName.endsWith('.csv')) {
    return null
  }

  if (
    lowerName.includes('molecule_scores') ||
    lowerName.includes('score') ||
    lowerName.includes('ranked') ||
    lowerName.includes('qed') ||
    lowerName.includes('sa_score') ||
    lowerName.includes('synthetic_accessibility') ||
    lowerName.includes('vina')
  ) {
    return file
  }

  return null
}

export function preferTopRankedSdfFiles<T extends TaskFileReference>(
  files: T[] | undefined
): T[] {
  const topRankedSdfFiles = (files || []).filter(file => {
    const lowerName = getFileName(file).toLowerCase()
    return lowerName.endsWith('.sdf') && (
      lowerName.includes('top10_molecules') ||
      lowerName.includes('top_10_molecules') ||
      lowerName.includes('top-ranked')
    )
  })

  return topRankedSdfFiles.length ? topRankedSdfFiles : (files || [])
}

export function rankSdfEntriesByScore(
  entries: VisualizationSceneEntry[],
  csvText: string,
  limit = TOP_RANKED_SDF_LIMIT
): VisualizationSceneEntry[] {
  const ranking = parseScoreRanking(csvText)
  if (!ranking) {
    return entries
  }

  const scoredEntries: Array<VisualizationSceneEntry & { __score: number }> = []

  for (const entry of entries) {
    const recordScore = typeof entry.sdfRecordIndex === 'number'
      ? ranking.scoresByRecordIndex.get(entry.sdfRecordIndex)
      : undefined
    const fileScore = entryFileKeyCandidates(entry)
      .map(candidate => ranking.scoresByFileKey.get(candidate))
      .find((value): value is number => typeof value === 'number')
    const score = recordScore ?? fileScore

    if (typeof score !== 'number') {
      continue
    }

    scoredEntries.push({
      ...entry,
      scoreLabel: `${ranking.label} ${score.toFixed(3)}`,
      __score: score
    })
  }

  const rankedEntries = scoredEntries
    .sort((left, right) =>
      ranking.higherIsBetter ? right.__score - left.__score : left.__score - right.__score
    )
    .slice(0, limit)
    .map(({ __score: _score, ...entry }) => entry)

  return rankedEntries.length ? rankedEntries : entries
}

export async function rankSdfEntriesByScoreFile(
  entries: VisualizationSceneEntry[],
  file: TaskFileReference | null | undefined
): Promise<VisualizationSceneEntry[]> {
  if (!file?.url) {
    return entries
  }

  const csvText = await fetchProtectedFileText(file.url)
  return rankSdfEntriesByScore(entries, csvText)
}
