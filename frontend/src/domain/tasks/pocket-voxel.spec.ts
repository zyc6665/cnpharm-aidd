import { describe, expect, it } from 'vitest'
import { parsePocketVoxelBoxes } from './pocket-voxel'

describe('parsePocketVoxelBoxes', () => {
  it('turns ATOM/HETATM records into voxel boxes', () => {
    const pdb = [
      'ATOM      1  C   UNL     1      20.271   4.822  48.343  1.00  0.00           C',
      'HETATM    2  C   UNL     1      22.271   4.822  48.343  1.00  0.00           C',
      'REMARK ignored',
      'ATOM      3  C   UNL     1      bad      1.000   2.000',
    ].join('\n')

    expect(parsePocketVoxelBoxes(pdb, 0.8)).toEqual([
      { center: [20.271, 4.822, 48.343], halfSize: 0.8 },
      { center: [22.271, 4.822, 48.343], halfSize: 0.8 },
    ])
  })

  it('returns an empty list for files without coordinates', () => {
    expect(parsePocketVoxelBoxes('REMARK empty')).toEqual([])
  })
})
