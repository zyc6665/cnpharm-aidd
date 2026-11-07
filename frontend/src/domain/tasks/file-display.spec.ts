import { describe, expect, it } from 'vitest'
import { toDisplayFileName } from './file-display'

describe('toDisplayFileName', () => {
  it('strips POSIX and Windows directory prefixes', () => {
    expect(toDisplayFileName('artifacts/lv_results/protein/pocket0.pdb')).toBe('pocket0.pdb')
    expect(toDisplayFileName('artifacts\\lv_results\\protein\\pocket0.pdb')).toBe('pocket0.pdb')
  })

  it('keeps bare filenames and tolerates empty values', () => {
    expect(toDisplayFileName('pocket0.pdb')).toBe('pocket0.pdb')
    expect(toDisplayFileName('')).toBe('')
    expect(toDisplayFileName(undefined)).toBe('')
  })
})
