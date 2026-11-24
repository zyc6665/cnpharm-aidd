import { describe, expect, it } from 'vitest'
import { downsampleSeries } from './analysis'

describe('MD result chart sampling', () => {
  it('preserves extrema while limiting display samples', () => {
    const rows = Array.from({ length: 2000 }, (_, index) => ({ time_ps: index, rmsd_nm: index === 1001 ? 99 : 1 }))
    const sampled = downsampleSeries(rows, 100, row => row.rmsd_nm)
    expect(sampled.length).toBeLessThanOrEqual(100)
    expect(sampled[0]?.time_ps).toBe(0)
    expect(sampled[sampled.length - 1]?.time_ps).toBe(1999)
    expect(sampled.some(row => row.rmsd_nm === 99)).toBe(true)
  })
})
