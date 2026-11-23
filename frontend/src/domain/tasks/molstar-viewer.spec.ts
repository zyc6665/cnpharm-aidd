import { describe, expect, it } from 'vitest'
import {
  DEFAULT_CO_LIGAND_RESIDUE_ID,
  resolveMolstarColorThemeOptions,
  resolveMolstarEffectiveColorTheme,
  resolveMolstarHierarchyPreset,
  resolveMolstarPocketSelection,
  resolveMolstarReprType,
  resolveMolstarRepresentationOptions,
  resolveMolstarSceneMode,
  resolveMolstarStructureArtifactMode,
  resolveMolstarStructureMode,
  resolveMolstarViewerPreset,
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
    expect(resolveMolstarHierarchyPreset('spacefill')).toBe('atomic-detail')
  })

  it('maps representations to concrete Mol* BuiltIn representation types', () => {
    expect(resolveMolstarReprType('cartoon')).toBe('cartoon')
    expect(resolveMolstarReprType('surface')).toBe('molecular-surface')
    expect(resolveMolstarReprType('spacefill')).toBe('spacefill')
    expect(resolveMolstarReprType('ball-and-stick')).toBe('ball-and-stick')
  })
})

describe('resolveMolstarViewerPreset', () => {
  it('preserves a small-molecule ball-and-stick default without enabling controls', () => {
    expect(resolveMolstarViewerPreset('molecule')).toMatchObject({
      mode: 'molecule',
      background: 'dark',
      primaryRepresentation: 'ball-and-stick',
      defaultColorTheme: 'element-symbol',
      showControls: false,
    })
  })

  it.each(['protein', 'pocket', 'docking'] as const)('uses cartoon for %s without changing legacy dark background', mode => {
    expect(resolveMolstarViewerPreset(mode)).toMatchObject({
      mode,
      background: 'dark',
      primaryRepresentation: 'cartoon',
      defaultColorTheme: 'chain-id',
      showControls: false,
    })
  })
})

describe('PyMOL-like toolbar options & artifact mode inference', () => {
  it('exposes appropriate representation and color options for protein vs molecule mode', () => {
    expect(resolveMolstarRepresentationOptions('protein')).toEqual([
      'cartoon',
      'surface',
      'ball-and-stick',
      'spacefill',
    ])
    expect(resolveMolstarRepresentationOptions('molecule')).toEqual([
      'ball-and-stick',
      'spacefill',
      'surface',
    ])

    expect(resolveMolstarColorThemeOptions('protein')).toContain('uncertainty')
    expect(resolveMolstarColorThemeOptions('protein')).toContain('secondary-structure')
    expect(resolveMolstarColorThemeOptions('molecule')).toEqual(['default', 'element-symbol', 'uniform'])
  })

  it('resolves default color themes per mode', () => {
    expect(resolveMolstarEffectiveColorTheme('protein', 'default')).toBe('chain-id')
    expect(resolveMolstarEffectiveColorTheme('molecule', 'default')).toBe('element-symbol')
    expect(resolveMolstarEffectiveColorTheme('protein', 'uncertainty')).toBe('uncertainty')
  })

  it('infers artifact mode from explicitMode, role, artifactType, and format', () => {
    expect(resolveMolstarStructureArtifactMode({ explicitMode: 'docking', role: 'ligand' })).toBe('docking')
    expect(resolveMolstarStructureArtifactMode({ role: 'receptor' })).toBe('protein')
    expect(resolveMolstarStructureArtifactMode({ role: 'pocket' })).toBe('pocket')
    expect(resolveMolstarStructureArtifactMode({ role: 'ligand' })).toBe('molecule')
    expect(resolveMolstarStructureArtifactMode({ role: 'structure', artifactType: 'protein_structure@1' })).toBe('protein')
    expect(resolveMolstarStructureArtifactMode({ role: 'structure', artifactType: 'md_trajectory' })).toBe('protein')
    expect(resolveMolstarStructureArtifactMode({ role: 'structure', artifactType: 'binding_pocket' })).toBe('pocket')
    expect(resolveMolstarStructureArtifactMode({ role: 'structure', format: 'pdb' })).toBe('protein')
    expect(resolveMolstarStructureArtifactMode({ role: 'structure', format: 'sdf' })).toBe('molecule')
  })

  it('infers scene mode for task visualization scenes', () => {
    expect(resolveMolstarSceneMode([{ role: 'receptor', format: 'pdb' }, { role: 'ligand', format: 'sdf' }])).toBe('docking')
    expect(resolveMolstarSceneMode([{ role: 'pocket', format: 'pdb' }])).toBe('pocket')
    expect(resolveMolstarSceneMode([{ role: 'structure', format: 'mmcif' }])).toBe('protein')
    expect(resolveMolstarSceneMode([{ role: 'ligand', format: 'sdf' }])).toBe('molecule')
  })
})
