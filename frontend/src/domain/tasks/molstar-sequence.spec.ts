import { describe, expect, it } from 'vitest'
import {
  groupSelectedResiduesByChain,
  residueSelectionKey,
  shouldShowSequenceRulerTick,
  toggleSequenceResidueSelection,
  toOneLetterResidue,
  type SequenceChain,
} from './molstar-sequence'

const sampleChains: SequenceChain[] = [
  {
    chain: 'A',
    residues: [
      { key: 'A:1', chain: 'A', seqId: 1, compId: 'MET', oneLetter: 'M' },
      { key: 'A:2', chain: 'A', seqId: 2, compId: 'ALA', oneLetter: 'A' },
      { key: 'A:3', chain: 'A', seqId: 3, compId: 'GLY', oneLetter: 'G' },
      { key: 'A:4', chain: 'A', seqId: 4, compId: 'LEU', oneLetter: 'L' },
    ],
  },
  {
    chain: 'B',
    residues: [
      { key: 'B:10', chain: 'B', seqId: 10, compId: 'TRP', oneLetter: 'W' },
    ],
  },
]

describe('molstar-sequence', () => {
  it('maps 3-letter amino acid codes including protonation/non-standard variants', () => {
    expect(toOneLetterResidue('ALA')).toBe('A')
    expect(toOneLetterResidue('mse')).toBe('M')
    expect(toOneLetterResidue('HID')).toBe('H')
    expect(toOneLetterResidue('SEC')).toBe('U')
    expect(toOneLetterResidue('LIG')).toBe('X')
  })

  it('toggles individual residues and supports Shift+Click continuous range within a chain', () => {
    const first = toggleSequenceResidueSelection({
      chains: sampleChains,
      currentSelectedKeys: [],
      clickedChain: 'A',
      clickedSeqId: 1,
      lastAnchorKey: null,
      shiftKey: false,
    })
    expect(first).toEqual({ selectedKeys: ['A:1'], anchorKey: 'A:1' })

    const range = toggleSequenceResidueSelection({
      chains: sampleChains,
      currentSelectedKeys: first.selectedKeys,
      clickedChain: 'A',
      clickedSeqId: 4,
      lastAnchorKey: first.anchorKey,
      shiftKey: true,
    })
    expect(range.selectedKeys).toEqual(['A:1', 'A:2', 'A:3', 'A:4'])

    const toggledOff = toggleSequenceResidueSelection({
      chains: sampleChains,
      currentSelectedKeys: range.selectedKeys,
      clickedChain: 'A',
      clickedSeqId: 2,
      lastAnchorKey: range.anchorKey,
      shiftKey: false,
    })
    expect(toggledOff.selectedKeys).toEqual(['A:1', 'A:3', 'A:4'])
  })

  it('groups selected residue keys by chain sorted numerically', () => {
    const keys = [
      residueSelectionKey('A', 12),
      residueSelectionKey('B', 5),
      residueSelectionKey('A', 3),
    ]
    expect(groupSelectedResiduesByChain(keys)).toEqual([
      { chain: 'A', seqIds: [3, 12] },
      { chain: 'B', seqIds: [5] },
    ])
  })

  it('shows ruler ticks at start, multiples of 10, and end', () => {
    expect(shouldShowSequenceRulerTick(0, 1, 25)).toBe(true)
    expect(shouldShowSequenceRulerTick(4, 5, 25)).toBe(false)
    expect(shouldShowSequenceRulerTick(9, 10, 25)).toBe(true)
    expect(shouldShowSequenceRulerTick(24, 25, 25)).toBe(true)
  })
})
