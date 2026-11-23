import { describe, expect, it } from 'vitest'
import {
  DEFAULT_CO_LIGAND_RESIDUE_ID,
  resolveMolstarHierarchyPreset,
  resolveMolstarPocketSelection,
  resolveMolstarStructureMode,
  resolveMolstarViewerPreset
} from './molstar-viewer'

describe('resolveMolstarPocketSelection', () => {
  it('deduplicates pocket residues and restricts selected residues to the pocket', () => {
    expect(resolveMolstarPocketSelection({ chain: 'A', residueIds: [10, 10, 11], selectedResidueIds: [11, 12, 11] })).toEqual({
      chain: 'A', residueIds: [10, 11], selectedResidueIds: [11],
    })
  })

  it('keeps co-ligand numbering stable', () => {
    expect(DEFAULT_CO_LIGAND_RESIDUE_ID).toBe(601)
  })
})

describe('resolveMolstarStructureMode', () => {
  it('selects protein only for receptor-containing scenes', () => {
    expect(resolveMolstarStructureMode(true)).toBe('protein')
    expect(resolveMolstarStructureMode(false)).toBe('molecule')
  })
})

describe('resolveMolstarHierarchyPreset', () => {
  it('maps shared representations to initial Mol* hierarchy presets', () => {
    expect(resolveMolstarHierarchyPreset('cartoon')).toBe('polymer-cartoon')
    expect(resolveMolstarHierarchyPreset('surface')).toBe('molecular-surface')
    expect(resolveMolstarHierarchyPreset('ball-and-stick')).toBe('atomic-detail')
    expect(resolveMolstarHierarchyPreset('sticks')).toBe('atomic-detail')
    expect(resolveMolstarHierarchyPreset('points')).toBe('atomic-detail')
  })
})

describe('resolveMolstarViewerPreset', () => {
  it('preserves a small-molecule ball-and-stick default without enabling controls', () => {
    expect(resolveMolstarViewerPreset('molecule')).toMatchObject({
      mode: 'molecule', background: 'dark', primaryRepresentation: 'ball-and-stick', showControls: false,
    })
  })

  it.each(['protein', 'pocket', 'docking'] as const)('uses cartoon for %s without changing legacy dark background', mode => {
    expect(resolveMolstarViewerPreset(mode)).toMatchObject({
      mode, background: 'dark', primaryRepresentation: 'cartoon', showControls: false,
    })
  })
})
