import { describe, expect, it } from 'vitest'
import { downsampleSeries, toFiniteNumber } from './analysis'

describe('MD analysis helpers', () => {
  it('treats blank numeric values as missing and explicit zero as valid', () => {
    expect(toFiniteNumber('')).toBeNull()
    expect(toFiniteNumber('  ')).toBeNull()
    expect(toFiniteNumber('0')).toBe(0)
  })
  it('preserves first, last, and bucket extrema during downsampling', () => {
    const values = Array.from({ length: 1000 }, (_, index) => ({ x: index, y: index === 501 ? 100 : index === 502 ? -50 : 1 }))
    const sampled = downsampleSeries(values, 20, item => item.y)
    expect(sampled[0]?.x).toBe(0)
    expect(sampled[sampled.length - 1]?.x).toBe(999)
    expect(sampled.some(item => item.y === 100)).toBe(true)
    expect(sampled.some(item => item.y === -50)).toBe(true)
  })
})
