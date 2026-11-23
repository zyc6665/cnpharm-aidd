export type MolstarViewerMode = 'molecule' | 'protein' | 'pocket' | 'docking'
export type MolstarRepresentation = 'cartoon' | 'surface' | 'sticks' | 'ball-and-stick' | 'spacefill' | 'points'
export type MolstarBackground = 'dark' | 'white'
export type MolstarColorTheme =
  | 'default'
  | 'chain-id'
  | 'element-symbol'
  | 'secondary-structure'
  | 'uncertainty'
  | 'hydrophobicity'
  | 'uniform'

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
  defaultColorTheme: MolstarColorTheme
  showControls: boolean
}

/** Domain-specific defaults are deliberate; shared engine does not imply shared presentation. */
export const MOLSTAR_VIEWER_PRESETS: Readonly<Record<MolstarViewerMode, MolstarViewerPreset>> = {
  molecule: {
    mode: 'molecule',
    background: 'dark',
    primaryRepresentation: 'ball-and-stick',
    defaultColorTheme: 'element-symbol',
    showControls: false,
  },
  protein: {
    mode: 'protein',
    background: 'dark',
    primaryRepresentation: 'cartoon',
    defaultColorTheme: 'chain-id',
    showControls: false,
  },
  pocket: {
    mode: 'pocket',
    background: 'dark',
    primaryRepresentation: 'cartoon',
    defaultColorTheme: 'chain-id',
    showControls: false,
  },
  docking: {
    mode: 'docking',
    background: 'dark',
    primaryRepresentation: 'cartoon',
    defaultColorTheme: 'chain-id',
    showControls: false,
  },
}

export function resolveMolstarViewerPreset(mode: MolstarViewerMode): MolstarViewerPreset {
  return MOLSTAR_VIEWER_PRESETS[mode]
}

/** Maps shared representations to Mol* hierarchy presets. */
export function resolveMolstarHierarchyPreset(
  representation: MolstarRepresentation,
): 'polymer-cartoon' | 'molecular-surface' | 'atomic-detail' {
  if (representation === 'cartoon') return 'polymer-cartoon'
  if (representation === 'surface') return 'molecular-surface'
  return 'atomic-detail'
}

/** Maps shared representations to Mol* StructureRepresentationRegistry BuiltIn type names. */
export function resolveMolstarReprType(
  representation: MolstarRepresentation,
): 'cartoon' | 'molecular-surface' | 'ball-and-stick' | 'spacefill' {
  if (representation === 'cartoon') return 'cartoon'
  if (representation === 'surface') return 'molecular-surface'
  if (representation === 'spacefill') return 'spacefill'
  return 'ball-and-stick'
}

const PROTEIN_REPRESENTATIONS: readonly MolstarRepresentation[] = [
  'cartoon',
  'surface',
  'ball-and-stick',
  'spacefill',
]

const MOLECULE_REPRESENTATIONS: readonly MolstarRepresentation[] = [
  'ball-and-stick',
  'sticks',
  'spacefill',
  'surface',
]

export function resolveMolstarRepresentationOptions(
  mode: MolstarViewerMode,
): readonly MolstarRepresentation[] {
  return mode === 'molecule' ? MOLECULE_REPRESENTATIONS : PROTEIN_REPRESENTATIONS
}

const PROTEIN_COLOR_THEMES: readonly MolstarColorTheme[] = [
  'default',
  'chain-id',
  'secondary-structure',
  'uncertainty',
  'hydrophobicity',
  'element-symbol',
  'uniform',
]

const MOLECULE_COLOR_THEMES: readonly MolstarColorTheme[] = [
  'default',
  'element-symbol',
  'uniform',
]

export function resolveMolstarColorThemeOptions(
  mode: MolstarViewerMode,
): readonly MolstarColorTheme[] {
  return mode === 'molecule' ? MOLECULE_COLOR_THEMES : PROTEIN_COLOR_THEMES
}

/** Resolves `'default'` to the concrete built-in Mol* color theme name for the given mode. */
export function resolveMolstarEffectiveColorTheme(
  mode: MolstarViewerMode,
  theme: MolstarColorTheme,
): Exclude<MolstarColorTheme, 'default'> {
  if (theme !== 'default') {
    return theme
  }
  const presetTheme = resolveMolstarViewerPreset(mode).defaultColorTheme
  return presetTheme === 'default' ? 'element-symbol' : presetTheme
}

/** Protein structures use the protein preset; ligand-only artifacts retain molecule defaults. */
export function resolveMolstarStructureMode(hasReceptor: boolean): 'molecule' | 'protein' {
  return hasReceptor ? 'protein' : 'molecule'
}

export function resolveMolstarSceneMode(
  entries: ReadonlyArray<{ role?: string; format?: string }>,
): MolstarViewerMode {
  const hasReceptor = entries.some(entry => entry.role === 'receptor')
  const hasLigand = entries.some(entry => entry.role === 'ligand')
  const hasPocket = entries.some(entry => entry.role === 'pocket')

  if (hasReceptor && hasLigand) {
    return 'docking'
  }
  if (hasPocket) {
    return 'pocket'
  }
  if (hasReceptor) {
    return 'protein'
  }
  const hasPolymerFormat = entries.some(
    entry => entry.format === 'pdb' || entry.format === 'mmcif' || entry.format === 'pdbqt',
  )
  return hasPolymerFormat ? 'protein' : 'molecule'
}

export interface MolstarArtifactModeInput {
  explicitMode?: MolstarViewerMode
  role?: 'structure' | 'receptor' | 'ligand' | 'pocket'
  artifactType?: string | null
  format?: string | null
}

/** Infers the Mol* viewer mode for artifact previews when callers omit an explicit `mode` prop. */
export function resolveMolstarStructureArtifactMode(input: MolstarArtifactModeInput): MolstarViewerMode {
  if (input.explicitMode) {
    return input.explicitMode
  }

  if (input.role === 'receptor') {
    return 'protein'
  }
  if (input.role === 'pocket') {
    return 'pocket'
  }
  if (input.role === 'ligand') {
    return 'molecule'
  }

  const normalizedType = (input.artifactType || '').split('@', 1)[0]?.toLowerCase() || ''
  if (normalizedType === 'protein_structure' || normalizedType === 'md_trajectory') {
    return 'protein'
  }
  if (normalizedType === 'binding_pocket') {
    return 'pocket'
  }
  if (normalizedType === 'ligand_structure' || normalizedType === 'molecule_table') {
    return 'molecule'
  }

  const normalizedFormat = (input.format || '').toLowerCase()
  if (normalizedFormat === 'pdb' || normalizedFormat === 'mmcif' || normalizedFormat === 'pdbqt') {
    return 'protein'
  }

  return 'molecule'
}
