import { describe, expect, it } from 'vitest'
import { buildAffinityComparison } from './affinityComparison'
import type { CsvPreviewRow } from '@/domain/tasks/csv-result'

function row(index: number, affinity: number, moleculeId: string, ligand = 0, pocket = 0): CsvPreviewRow {
  return {
    __rowKey: String(index),
    molecule_id: moleculeId,
    complex_id: `C-${moleculeId}`,
    duration_sec: '20',
    'prediction.predicted_affinity': String(affinity),
    'prediction.predicted_ligand_to_pocket': String(ligand),
    'prediction.predicted_pocket_to_ligand': String(pocket),
    'prediction.scale': 'pKa/pKi-like score',
    'preprocessing.pocket_atom_count': '80',
    'preprocessing.ligand_atom_count': '10'
  }
}

const rows = [
  row(0, 4.062, 'M1', 4.9, 3.224),
  row(1, 3.42, 'M2', 4.4, 3.0),
  row(2, 3.2, 'M3', 4.0, 2.8),
  row(3, 2.1, 'M4', 3.1, 2.0)
]

describe('buildAffinityComparison', () => {
  it('ranks candidates by predicted affinity and reports the delta to the median', () => {
    const result = buildAffinityComparison(rows, rows[0]!)
    expect(result.total).toBe(4)
    expect(result.rank).toBe(1)
    expect(result.quality).toBe('best')
    expect(result.percentile).toBe(100)
    expect(result.median).toBeCloseTo(3.31)
    expect(result.deltaToMedian).toBeCloseTo(0.752)
    expect(result.gapToBest).toBe(0)
    expect(result.scale).toBe('pKa/pKi-like score')
  })

  it('finds the current row and reports the gap to the best candidate', () => {
    const result = buildAffinityComparison(rows, rows[3]!)
    expect(result.rank).toBe(4)
    expect(result.quality).toBe('low')
    expect(result.gapToBest).toBeCloseTo(-1.962)
    expect(result.current?.moleculeId).toBe('M4')
  })

  it('handles a single candidate without inventing a comparison', () => {
    const result = buildAffinityComparison([rows[1]!], rows[1]!)
    expect(result.total).toBe(1)
    expect(result.quality).toBe('single')
    expect(result.rank).toBe(1)
    expect(result.gapToBest).toBe(0)
  })

  it('ignores rows without a numeric predicted affinity', () => {
    const broken: CsvPreviewRow = { __rowKey: '9', molecule_id: 'MX', 'prediction.predicted_affinity': '' }
    const result = buildAffinityComparison([...rows, broken], rows[1]!)
    expect(result.total).toBe(4)
    expect(result.candidates.map(item => item.moleculeId)).not.toContain('MX')
  })
})
