import type { Task } from '../../types/models'
import type { BuiltInTrajectoryFormat } from 'molstar/lib/mol-plugin-state/formats/trajectory'

type SupportedVisualizationFormat = Extract<
  BuiltInTrajectoryFormat,
  'pdb' | 'mmcif' | 'pdbqt' | 'sdf' | 'mol2'
>

type FileSource = 'input' | 'output'
type VisualizationRole = 'structure' | 'receptor' | 'ligand'

export interface TaskFileReference {
  id?: string | number
  original_name?: string
  filename?: string
  content_type?: string
  size?: number
  url?: string
  relative_path?: string
}

export interface VisualizationSceneEntry {
  key: string
  url: string
  label: string
  source: FileSource
  role: VisualizationRole
  format: SupportedVisualizationFormat
  extension: string
  relativePath?: string
  scoreLabel?: string
  sdfRecordIndex?: number
}

export interface VisualizationScene {
  entries: VisualizationSceneEntry[]
  inputEntries: VisualizationSceneEntry[]
  outputEntries: VisualizationSceneEntry[]
  supportedOutputFiles: VisualizationSceneEntry[]
  unsupportedOutputFiles: TaskFileReference[]
  hasRenderableOutput: boolean
  selectedOutputKey: string | null
}

const FORMAT_BY_EXTENSION: Record<string, SupportedVisualizationFormat> = {
  '.pdb': 'pdb',
  '.cif': 'mmcif',
  '.mmcif': 'mmcif',
  '.pdbqt': 'pdbqt',
  '.sdf': 'sdf',
  '.mol2': 'mol2'
}

const SMALL_MOLECULE_EXTENSIONS = new Set(['.sdf', '.mol2'])
const STRUCTURE_EXTENSIONS = new Set(['.pdb', '.cif', '.mmcif', '.pdbqt'])

function getFileLabel(file: TaskFileReference): string {
  return file.original_name || file.filename || String(file.id || 'unnamed-file')
}

function getFileExtension(file: TaskFileReference): string {
  const rawName = file.original_name || file.filename || file.url || ''
  const baseName = (rawName.split('?')[0] || '').split('#')[0] || ''
  const lowerName = baseName.toLowerCase()

  for (const extension of Object.keys(FORMAT_BY_EXTENSION)) {
    if (lowerName.endsWith(extension)) {
      return extension
    }
  }

  return ''
}

function getRoleByExtension(extension: string, source: FileSource): VisualizationRole {
  if (source === 'input' && STRUCTURE_EXTENSIONS.has(extension)) {
    return 'receptor'
  }

  if (SMALL_MOLECULE_EXTENSIONS.has(extension)) {
    return 'ligand'
  }

  return 'structure'
}

function buildRenderableEntries(
  files: TaskFileReference[] | undefined,
  source: FileSource
): VisualizationSceneEntry[] {
  return (files || [])
    .filter((file): file is TaskFileReference & { url: string } => Boolean(file?.url))
    .map(file => {
      const extension = getFileExtension(file)
      const format = FORMAT_BY_EXTENSION[extension]

      if (!format) {
        return null
      }

      const entry: VisualizationSceneEntry = {
        key: `${source}-${file.id ?? getFileLabel(file)}`,
        url: file.url,
        label: getFileLabel(file),
        source,
        role: getRoleByExtension(extension, source),
        format,
        extension
      }

      if (file.relative_path) {
        entry.relativePath = file.relative_path
      }

      return entry
    })
    .filter((entry): entry is VisualizationSceneEntry => entry !== null)
}

function selectOutputEntry(
  outputEntries: VisualizationSceneEntry[],
  selectedOutputKey?: string | null
): VisualizationSceneEntry | null {
  if (!outputEntries.length) {
    return null
  }

  if (selectedOutputKey) {
    const selectedEntry = outputEntries.find(entry => entry.key === selectedOutputKey)
    if (selectedEntry) {
      return selectedEntry
    }
  }

  return outputEntries[0] || null
}

function buildFocusedEntries(
  inputEntries: VisualizationSceneEntry[],
  outputEntries: VisualizationSceneEntry[],
  selectedOutputKey?: string | null
): {
  entries: VisualizationSceneEntry[]
  selectedOutputKey: string | null
} {
  const selectedOutput = selectOutputEntry(outputEntries, selectedOutputKey)
  if (!selectedOutput) {
    return {
      entries: [],
      selectedOutputKey: null
    }
  }

  const fixedInputEntry =
    inputEntries.find(entry => entry.role === 'receptor') || inputEntries[0] || null

  return {
    entries: fixedInputEntry ? [fixedInputEntry, selectedOutput] : [selectedOutput],
    selectedOutputKey: selectedOutput.key
  }
}

export function createVisualizationScene(
  inputEntries: VisualizationSceneEntry[],
  outputEntries: VisualizationSceneEntry[],
  unsupportedOutputFiles: TaskFileReference[],
  selectedOutputKey?: string | null
): VisualizationScene {
  if (!outputEntries.length) {
    return {
      entries: [],
      inputEntries,
      outputEntries,
      supportedOutputFiles: outputEntries,
      unsupportedOutputFiles,
      hasRenderableOutput: false,
      selectedOutputKey: null
    }
  }

  const focused = buildFocusedEntries(inputEntries, outputEntries, selectedOutputKey)

  return {
    entries: focused.entries,
    inputEntries,
    outputEntries,
    supportedOutputFiles: outputEntries,
    unsupportedOutputFiles,
    hasRenderableOutput: true,
    selectedOutputKey: focused.selectedOutputKey
  }
}

export function detectVisualizationFormat(
  file: TaskFileReference
): SupportedVisualizationFormat | null {
  const extension = getFileExtension(file)
  return FORMAT_BY_EXTENSION[extension] || null
}

export function buildFocusedVisualizationScene(
  scene: VisualizationScene,
  selectedOutputKey?: string | null
): VisualizationScene {
  if (!scene.outputEntries.length) {
    return {
      ...scene,
      entries: [],
      selectedOutputKey: null
    }
  }

  const focused = buildFocusedEntries(
    scene.inputEntries,
    scene.outputEntries,
    selectedOutputKey || scene.selectedOutputKey
  )

  return {
    ...scene,
    entries: focused.entries,
    selectedOutputKey: focused.selectedOutputKey
  }
}

export function buildVisualizationScene(task?: Task | null): VisualizationScene {
  const outputFiles = task?.output_files || []
  const inputFiles = task?.input_files || []

  const outputEntries = buildRenderableEntries(outputFiles, 'output')
  const inputEntries = buildRenderableEntries(inputFiles, 'input')
  const unsupportedOutputFiles = outputFiles.filter(file => !detectVisualizationFormat(file))

  return createVisualizationScene(inputEntries, outputEntries, unsupportedOutputFiles)
}
