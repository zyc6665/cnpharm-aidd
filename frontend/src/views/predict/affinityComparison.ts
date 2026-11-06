import type { CsvPreviewRow } from '@/domain/tasks/csv-result'

export const AFFINITY_FIELD_ALIASES = {
  moleculeId: ['molecule_id'],
  complexId: ['complex_id'],
  duration: ['duration_sec'],
  predictedAffinity: ['prediction.predicted_affinity', 'predicted_affinity'],
  ligandToPocket: ['prediction.predicted_ligand_to_pocket', 'predicted_ligand_to_pocket'],
  pocketToLigand: ['prediction.predicted_pocket_to_ligand', 'predicted_pocket_to_ligand'],
  scale: ['prediction.scale', 'scale'],
  pocketAtoms: ['preprocessing.pocket_atom_count', 'pocket_atom_count'],
  ligandAtoms: ['preprocessing.ligand_atom_count', 'ligand_atom_count'],
  pocketBonds: ['preprocessing.pocket_bond_count', 'pocket_bond_count'],
  ligandBonds: ['preprocessing.ligand_bond_count', 'ligand_bond_count'],
  generatedPocketAtoms: ['preprocessing.generated_pocket_atom_count', 'generated_pocket_atom_count']
} as const

export type AffinityField = keyof typeof AFFINITY_FIELD_ALIASES

export interface AffinityCandidate {
  row: CsvPreviewRow
  rowKey: string
  moleculeId: string
  affinity: number
  ligandToPocket: number | null
  pocketToLigand: number | null
  duration: number | null
  /** 1-based rank; ties share the same rank. */
  rank: number
}

export interface AffinityComparison {
  current: AffinityCandidate | null
  candidates: AffinityCandidate[]
  total: number
  rank: number
  median: number | null
  best: AffinityCandidate | null
  deltaToMedian: number | null
  gapToBest: number | null
  quality: 'single' | 'best' | 'top' | 'middle' | 'low'
  /** Percent of other candidates this molecule beats (0-100). */
  percentile: number
  scale: string
}

function normalize(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, '')
}

function normalizedRow(row: CsvPreviewRow): Map<string, string> {
  const map = new Map<string, string>()
  for (const [key, value] of Object.entries(row)) {
    map.set(normalize(key), String(value ?? '').trim())
  }
  return map
}

export function readAffinityField(row: CsvPreviewRow, field: AffinityField): string {
  const map = normalizedRow(row)
  for (const alias of AFFINITY_FIELD_ALIASES[field]) {
    const value = map.get(normalize(alias))
    if (value) {
      return value
    }
  }
  return ''
}

export function readAffinityNumber(row: CsvPreviewRow, field: AffinityField): number | null {
  const text = readAffinityField(row, field)
  if (!text) {
    return null
  }
  const value = Number(text)
  return Number.isFinite(value) ? value : null
}

function median(values: number[]): number | null {
  if (!values.length) {
    return null
  }
  const sorted = [...values].sort((left, right) => left - right)
  const middle = Math.floor(sorted.length / 2)
  if (sorted.length % 2 === 1) {
    return sorted[middle] ?? null
  }
  const lower = sorted[middle - 1]
  const upper = sorted[middle]
  return lower === undefined || upper === undefined ? null : (lower + upper) / 2
}

function toCandidate(row: CsvPreviewRow): AffinityCandidate | null {
  const affinity = readAffinityNumber(row, 'predictedAffinity')
  if (affinity === null) {
    return null
  }
  const rowKey = String(row.__rowKey ?? '')
  return {
    row,
    rowKey,
    moleculeId: readAffinityField(row, 'moleculeId') || rowKey || '-',
    affinity,
    ligandToPocket: readAffinityNumber(row, 'ligandToPocket'),
    pocketToLigand: readAffinityNumber(row, 'pocketToLigand'),
    duration: readAffinityNumber(row, 'duration'),
    rank: 0
  }
}

/**
 * Build candidate-level comparison for affinity result details.
 * Ranking is based on the model's predicted affinity only; no hard-coded
 * biological thresholds are invented.
 */
export function buildAffinityComparison(rows: CsvPreviewRow[], currentRow: CsvPreviewRow): AffinityComparison {
  const candidates = rows
    .map(toCandidate)
    .filter((candidate): candidate is AffinityCandidate => Boolean(candidate))
    .sort((left, right) => {
      if (right.affinity !== left.affinity) {
        return right.affinity - left.affinity
      }
      return left.moleculeId.localeCompare(right.moleculeId)
    })

  for (const candidate of candidates) {
    candidate.rank = 1 + candidates.filter(other => other.affinity > candidate.affinity).length
  }

  const currentKey = String(currentRow.__rowKey ?? '')
  const current = candidates.find(candidate => candidate.row === currentRow)
    ?? candidates.find(candidate => candidate.rowKey === currentKey)
    ?? null

  const values = candidates.map(candidate => candidate.affinity)
  const total = candidates.length
  const rank = current?.rank ?? 0
  const best = candidates[0] ?? null
  const medianValue = median(values)
  const deltaToMedian = current && medianValue !== null ? current.affinity - medianValue : null
  const gapToBest = current && best ? current.affinity - best.affinity : null
  const percentile = total > 1 && rank > 0
    ? Math.round(((total - rank) / (total - 1)) * 100)
    : total <= 1 ? 100 : 0

  let quality: AffinityComparison['quality'] = 'low'
  if (total <= 1) {
    quality = 'single'
  } else if (rank === 1) {
    quality = 'best'
  } else if (rank <= Math.max(1, Math.ceil(total * 0.25))) {
    quality = 'top'
  } else if (rank <= Math.ceil(total * 0.5)) {
    quality = 'middle'
  }

  return {
    current,
    candidates,
    total,
    rank,
    median: medianValue,
    best,
    deltaToMedian,
    gapToBest,
    quality,
    percentile,
    scale: current ? readAffinityField(current.row, 'scale') : ''
  }
}
