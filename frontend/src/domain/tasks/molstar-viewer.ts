export type MolstarViewerMode = 'molecule' | 'protein' | 'pocket' | 'docking'
export type MolstarRepresentation = 'cartoon' | 'surface' | 'sticks' | 'ball-and-stick' | 'points'
export type MolstarBackground = 'dark' | 'white'

export interface MolstarPocketSelection {
  chain: string
  residueIds: readonly number[]
  selectedResidueIds: readonly number[]
}

export const DEFAULT_CO_LIGAND_RESIDUE_ID = 601

export function resolveMolstarPocketSelection(selection: MolstarPocketSelection): MolstarPocketSelection {
  const residueIds = [...new Set(selection.residueIds)]
  const selectedResidueIds = [...new Set(selection.selectedResidueIds)].filter(id => residueIds.includes(id))
  return { chain: selection.chain, residueIds, selectedResidueIds }
}

export interface MolstarViewerPreset {
  mode: MolstarViewerMode
  background: MolstarBackground
  primaryRepresentation: MolstarRepresentation
  showControls: boolean
}

/** Domain-specific defaults are deliberate; shared engine does not imply shared presentation. */
export const MOLSTAR_VIEWER_PRESETS: Readonly<Record<MolstarViewerMode, MolstarViewerPreset>> = {
  molecule: { mode: 'molecule', background: 'dark', primaryRepresentation: 'ball-and-stick', showControls: false },
  protein: { mode: 'protein', background: 'dark', primaryRepresentation: 'cartoon', showControls: false },
  pocket: { mode: 'pocket', background: 'dark', primaryRepresentation: 'cartoon', showControls: false },
  docking: { mode: 'docking', background: 'dark', primaryRepresentation: 'cartoon', showControls: false },
}

export function resolveMolstarViewerPreset(mode: MolstarViewerMode): MolstarViewerPreset {
  return MOLSTAR_VIEWER_PRESETS[mode]
}

/** Maps shared representations to Mol* hierarchy presets. */
export function resolveMolstarHierarchyPreset(representation: MolstarRepresentation): 'polymer-cartoon' | 'molecular-surface' | 'atomic-detail' {
  if (representation === 'cartoon') return 'polymer-cartoon'
  if (representation === 'surface') return 'molecular-surface'
  return 'atomic-detail'
}

/** Protein structures use the protein preset; ligand-only artifacts retain molecule defaults. */
export function resolveMolstarStructureMode(hasReceptor: boolean): 'molecule' | 'protein' {
  return hasReceptor ? 'protein' : 'molecule'
}
