import { describe, expect, it } from 'vitest'
import { buildInlineSmilesCsv, createRequestTracker, parseInlineSmiles, rewriteSdfRecordsWithTitle } from './submission-smiles'

describe('submission smiles helpers', () => {
  it('parses quoted CSV cells and filters invalid rows', () => {
    const result = parseInlineSmiles('name,canonical_smiles\n"aspirin, parent","CC(=O)Oc1ccccc1C(=O)O"\nbad value')
    expect(result.validRows).toHaveLength(1)
    expect(result.validRows[0]?.name).toBe('aspirin, parent')
    expect(result.skippedCount).toBe(1)
  })
  it('escapes CSV and tracks request generations', () => {
    expect(buildInlineSmilesCsv([{ smiles: 'C,C' }])).toBe('smiles\n"C,C"')
    const tracker = createRequestTracker(); const first = tracker.next(); const second = tracker.next()
    expect(tracker.isCurrent(first)).toBe(false); expect(tracker.isCurrent(second)).toBe(true)
  })
  it('preserves blank SDF title/header lines', () => {
    const [record] = rewriteSdfRecordsWithTitle('\n  program\ncomment\n  0  0  0  0  0  0            999 V2000\n$$$$\n', 'mol')
    expect(record).toContain('mol_1\n  program\ncomment')
  })
})
