import type { Task } from '../../types/models'
import type { BuiltInTrajectoryFormat } from 'molstar/lib/mol-plugin-state/formats/trajectory'
import { buildArtifactVersionDownloadUrl } from '../../api/artifacts'
import type { TypedArtifact } from '../../types/artifacts'
import { detectCsvResultFile } from './csv-result'

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

export type VisualizationResultKind = 'structure' | 'csv' | 'file' | 'artifact'

export type VisualizationFilePreviewKind = 'text' | 'json' | 'image' | 'download'

export interface VisualizationResultItem {
  key: string
  label: string
  description: string
  kind: VisualizationResultKind
  extension?: string
  previewKind?: VisualizationFilePreviewKind
  entry?: VisualizationSceneEntry
  file?: TaskFileReference
  artifact?: TypedArtifact
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
const TEXT_FILE_EXTENSIONS = new Set([
  '.txt',
  '.log',
  '.md',
  '.markdown',
  '.yaml',
  '.yml',
  '.xml',
  '.html',
  '.htm',
  '.tsv',
  '.sh',
  '.py',
  '.js',
  '.ts'
])
const JSON_FILE_EXTENSIONS = new Set(['.json', '.geojson', '.jsonl'])
const IMAGE_FILE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'])
const JSON_CONTENT_TYPES = new Set(['application/json', 'application/geo+json', 'application/ld+json'])

function getFileLabel(file: TaskFileReference): string {
  return file.original_name || file.filename || String(file.id || 'unnamed-file')
}

function getFileExtension(file: TaskFileReference): string {
  const rawName = file.original_name || file.filename || file.url || ''
  const baseName = (rawName.split('?')[0] || '').split('#')[0] || ''
  const lowerName = baseName.toLowerCase()
  const extensionIndex = lowerName.lastIndexOf('.')
  return extensionIndex > 0 ? lowerName.slice(extensionIndex) : ''
}

function getFilePreviewKind(file: TaskFileReference): VisualizationFilePreviewKind {
  const extension = getFileExtension(file)
  const contentType = (file.content_type || '').toLowerCase().split(';')[0]?.trim() || ''

  if (JSON_FILE_EXTENSIONS.has(extension) || JSON_CONTENT_TYPES.has(contentType) || contentType.endsWith('+json')) {
    return 'json'
  }

  if (IMAGE_FILE_EXTENSIONS.has(extension) || contentType.startsWith('image/')) {
    return 'image'
  }

  if (
    TEXT_FILE_EXTENSIONS.has(extension) ||
    contentType.startsWith('text/') ||
    contentType === 'application/xml' ||
    contentType === 'application/yaml' ||
    contentType === 'application/x-yaml' ||
    contentType === 'application/javascript' ||
    contentType === 'application/sql'
  ) {
    return 'text'
  }

  return 'download'
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

const ARTIFACT_PREVIEW_ROLES: Record<string, string[]> = {
  protein_structure: ['prepared_pdb', 'structure_file', 'raw_structure_file'],
  binding_pocket: ['pocket_file', 'structure_file'],
  ligand_structure: ['structure_3d_sdf', 'structure_file', 'structure_2d_sdf'],
  molecule_table: ['structure_3d_sdf', 'structure_file', 'structure_2d_sdf'],
  // MD 轨迹的 DCD 不在 molstar `BuiltInTrajectoryFormat` 里，按既有约定只做
  // 拓扑结构的静态预览（完整轨迹文件仍可下载，RMSD/RMSF 曲线见任务 MD 结果页）。
  md_trajectory: ['topology_pdb', 'structure_file', 'structure_pdb'],
}

function normalizeArtifactType(artifact: TypedArtifact): string {
  return artifact.artifact_type.split('@', 1)[0] || artifact.artifact_type
}

function getArtifactFileReference(artifact: TypedArtifact): TaskFileReference {
  const version = artifact.latest_version
  const files = (version.files || [])
    .filter(file => Boolean(file.download_url))
    .sort((left, right) => left.sort_order - right.sort_order)
  const preferredRoles = ARTIFACT_PREVIEW_ROLES[normalizeArtifactType(artifact)] || []
  const selectedFile = preferredRoles
    .map(role => files.find(file => file.role === role))
    .find(Boolean) || files.find(file => file.is_primary) || files[0]

  return {
    id: selectedFile?.file_id || version.id,
    original_name: selectedFile?.filename || version.filename,
    filename: selectedFile?.filename || version.filename,
    content_type: selectedFile?.content_type || version.content_type || undefined,
    size: selectedFile?.size_bytes || version.size_bytes,
    url: selectedFile?.download_url || buildArtifactVersionDownloadUrl(artifact.id, version.id),
    relative_path: selectedFile?.role,
  }
}

function getArtifactRole(artifact: TypedArtifact, extension: string): VisualizationRole {
  const artifactType = normalizeArtifactType(artifact)

  if (artifactType === 'protein_structure') {
    return 'receptor'
  }

  if (
    artifactType === 'ligand_structure' ||
    artifactType === 'molecule_table' ||
    SMALL_MOLECULE_EXTENSIONS.has(extension)
  ) {
    return 'ligand'
  }

  return 'structure'
}

function buildArtifactResultItem(artifact: TypedArtifact): VisualizationResultItem {
  const file = getArtifactFileReference(artifact)
  const format = detectVisualizationFormat(file)

  if (detectCsvResultFile(file)) {
    return {
      key: `artifact-${artifact.id}-csv`,
      label: artifact.name || file.filename || 'CSV',
      description: 'CSV',
      kind: 'csv',
      extension: '.csv',
      file,
      artifact,
    }
  }

  if (format) {
    const extension = `.${format === 'mmcif' ? 'cif' : format}`
    const entry: VisualizationSceneEntry = {
      key: `artifact-${artifact.id}-structure`,
      url: file.url || '',
      label: artifact.name || file.filename || '结构结果',
      source: 'output',
      role: getArtifactRole(artifact, extension),
      format,
      extension,
      relativePath: file.relative_path,
    }

    return {
      key: entry.key,
      label: entry.label,
      description: extension.replace('.', '').toUpperCase(),
      kind: 'structure',
      extension,
      entry,
      artifact,
    }
  }

  return {
    key: `artifact-${artifact.id}`,
    label: artifact.name,
    description: artifact.semantic_type || artifact.artifact_type,
    kind: 'artifact',
    extension: getFileExtension(file) || undefined,
    artifact,
  }
}

function getFileIdentityValues(file: TaskFileReference): string[] {
  const identities = new Set<string>()

  for (const value of [file.id, file.url, file.original_name, file.filename]) {
    if (value === undefined || value === null || value === '') {
      continue
    }

    const withoutQuery = String(value).split('?')[0] || ''
    const withoutFragment = withoutQuery.split('#')[0] || ''
    const normalized = withoutFragment
      .replace(/\\/g, '/')
      .toLowerCase()
    identities.add(normalized)

    const basename = normalized.split('/').pop() || normalized
    if (basename.includes('.')) {
      identities.add(basename)
      identities.add(basename.split('__').pop() || basename)
    }
  }

  return Array.from(identities)
}

function hasSharedFileIdentity(left: TaskFileReference, right: TaskFileReference): boolean {
  const rightIdentities = new Set(getFileIdentityValues(right))
  return getFileIdentityValues(left).some(identity => rightIdentities.has(identity))
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

export function buildVisualizationResultItems(
  task?: Task | null,
  scene: VisualizationScene = buildVisualizationScene(task)
): VisualizationResultItem[] {
  const items: VisualizationResultItem[] = []
  const outputFiles = task?.output_files || []

  for (const entry of scene.outputEntries) {
    items.push({
      key: entry.key,
      label: entry.label,
      description: entry.scoreLabel || entry.extension.replace('.', '').toUpperCase(),
      kind: 'structure',
      extension: entry.extension,
      entry,
    })
  }

  for (const file of outputFiles) {
    if (!detectCsvResultFile(file) || items.some(item => item.file && hasSharedFileIdentity(item.file, file))) {
      continue
    }

    items.push({
      key: `output-csv-${file.id ?? file.url ?? getFileLabel(file)}`,
      label: getFileLabel(file),
      description: 'CSV',
      kind: 'csv',
      extension: '.csv',
      file,
    })
  }

  for (const file of outputFiles) {
    if (
      detectVisualizationFormat(file) ||
      detectCsvResultFile(file) ||
      items.some(item => item.file && hasSharedFileIdentity(item.file, file))
    ) {
      continue
    }

    const extension = getFileExtension(file)
    const previewKind = getFilePreviewKind(file)
    items.push({
      key: `output-file-${file.id ?? file.url ?? getFileLabel(file)}`,
      label: getFileLabel(file),
      description: extension ? extension.slice(1).toUpperCase() : previewKind.toUpperCase(),
      kind: 'file',
      extension: extension || undefined,
      previewKind,
      file,
    })
  }

  for (const artifact of task?.artifacts || []) {
    const artifactItem = buildArtifactResultItem(artifact)
    const artifactFile = artifactItem.file || (
      artifactItem.entry
        ? {
            id: artifactItem.entry.key,
            filename: artifactItem.entry.label,
            url: artifactItem.entry.url,
          }
        : null
    )

    if (
      artifactFile &&
      outputFiles.some(file => hasSharedFileIdentity(artifactFile, file))
    ) {
      continue
    }

    items.push(artifactItem)
  }

  return items
}
