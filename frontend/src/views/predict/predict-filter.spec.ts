import { describe, expect, it } from 'vitest'
import { filterPredictRows } from './predict-filter'
import type { CsvPreviewRow } from '@/domain/tasks/csv-result'

const rows: CsvPreviewRow[] = [
  { __rowKey: '1', molecule_id: 'M1', smiles: 'CCO', 'prediction.predicted_affinity': '4.062', hia: '0.9' },
  { __rowKey: '2', molecule_id: 'M2', smiles: 'CCC', 'prediction.predicted_affinity': '3.49', hia: '0.4' },
  { __rowKey: '3', molecule_id: 'M3', smiles: '', 'prediction.predicted_affinity': '2.1', hia: '0.7' }
]

describe('filterPredictRows', () => {
  it('filters affinity results by predicted affinity', () => {
    const result = filterPredictRows(rows, {
      isAffinityResult: true,
      affinityColumnKey: 'prediction.predicted_affinity',
      affinityMin: 3
    })
    expect(result.map(row => row.molecule_id)).toEqual(['M1', 'M2'])
  })

  it('does not filter when affinity min is empty', () => {
    const result = filterPredictRows(rows, {
      isAffinityResult: true,
      affinityColumnKey: 'prediction.predicted_affinity',
      affinityMin: null,
      column: 'hia',
      min: 0.99
    })
    expect(result).toHaveLength(3)
  })

  it('requires a selected column before applying min or max', () => {
    expect(filterPredictRows(rows, { min: 0.8 })).toHaveLength(3)
  })

  it('applies min and max to a numeric column', () => {
    const result = filterPredictRows(rows, { column: 'hia', min: 0.5, max: 0.8 })
    expect(result.map(row => row.molecule_id)).toEqual(['M3'])
  })

  it('only applies SMILES search when the table has a SMILES column', () => {
    expect(filterPredictRows(rows, { searchText: 'CCO', hasSmilesColumn: true })).toHaveLength(1)
    expect(filterPredictRows(rows, { searchText: 'CCO', hasSmilesColumn: false })).toHaveLength(3)
  })
})
