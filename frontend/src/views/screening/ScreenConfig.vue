<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import { uploadFile } from '@/api/files'
import { submitToolTask } from '@/api/screening'
import ModelSelect from '@/components/design/ModelSelect.vue'
import ModelParameterForm, { type ParameterFieldOverride } from '@/components/design/ModelParameterForm.vue'
import FragmentSketchModal from '@/components/design/FragmentSketchModal.vue'
import MoleculeInlineFragmentCard from '@/components/design/MoleculeInlineFragmentCard.vue'
import PocketCoordinatePanel, {
  type PocketCoordinateState,
  type PocketDefineMode,
  type PocketTestIds
} from '@/components/design/PocketCoordinatePanel.vue'
import { useModelOptions } from '@/composables/useModelOptions'
import { SCREENING_PARAM_DEFAULTS, SCREENING_PARAM_RANGES, VINA_TOOL_SLUG } from '@/types/screening'
import { LDDM_GENERATION_TOOL_SLUG } from '@/types/design'
import type { ScreeningParams } from '@/types/screening'
import { exportCandidateSet, listCandidateSets } from '@/api/compounds'
import { listProjects } from '@/api/projects'
import { getTarget, listStructures, listTargets } from '@/api/targets'
import { structureOptionLabel } from '@/domain/targets/structure-option'
import type { CandidateSet } from '@/types/compounds'
import type { ResearchProject } from '@/types/projects'
import type { ProteinDetail, ProteinStructureDetail, TargetSummary } from '@/types/targets'
import Smiles2DCell from '@/components/tasks/Smiles2DCell.vue'
import { useRequestSequence } from '@/composables/useRequestSequence'
import { buildInlineSmilesFile, escapeCsvCell, parseInlineSmiles, rewriteSdfRecordsWithTitle } from '@/domain/molecules/submission-smiles'
import { formatAtomIndices, parseAtomIndices, type FragmentMolecule } from '@/domain/molecules/fragment-graph'
import { parseAndNormalizeLigandUpload } from '@/domain/molecules/ligand-upload'
import {
  extractProteinHetatmPocketGeometry,
  parseReferenceLigandGeometry,
  type PocketGeometry
} from '@/domain/pockets/pocket-geometry'
import {
  buildDefaultValues,
  normalizeParameters,
  validateParameters,
  type ParameterValues
} from '@/domain/tools/parameterSchema'

const props = withDefaults(defineProps<{ projectIdOverride?: string }>(), { projectIdOverride: '' })
const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const {
  options: modelOptions,
  selectedSlug,
  selectedOption,
  loading: modelLoading,
  load: loadModels
} = useModelOptions('docking', {
  defaultSlug: VINA_TOOL_SLUG,
  includeSlugs: [LDDM_GENERATION_TOOL_SLUG]
})
void loadModels()

const displayModelOptions = computed(() =>
  modelOptions.value.map(option =>
    option.slug === LDDM_GENERATION_TOOL_SLUG
      ? {
          ...option,
          name: t('screening.config.lddmDockModelName'),
          description: t('screening.config.lddmDockModelDesc')
        }
      : option
  )
)
const isLddmDock = computed(() => selectedSlug.value === LDDM_GENERATION_TOOL_SLUG)

const projectId = computed(() => {
  if (props.projectIdOverride) return props.projectIdOverride
  const raw = route.query.project_id
  if (typeof raw === 'string' && raw) return raw
  const paramId = route.params?.projectId
  return typeof paramId === 'string' ? paramId : ''
})
const projects = ref<ResearchProject[]>([])
const projectOptions = computed(() => projects.value.map(item => ({ label: item.name, value: item.id })))
const receptorSource = ref<'upload' | 'project'>('upload')
const ligandSource = ref<'upload' | 'candidate' | 'inline'>('upload')
const requestTrackers = { targets: useRequestSequence(), proteins: useRequestSequence(), structures: useRequestSequence(), candidateSets: useRequestSequence(), ligandCount: useRequestSequence(), handoff: useRequestSequence() }
const targets = ref<TargetSummary[]>([])
const proteins = ref<ProteinDetail[]>([])
const structures = ref<ProteinStructureDetail[]>([])
const selectedTargetId = ref('')
const selectedProteinId = ref('')
const selectedStructureId = ref('')
const candidateSets = ref<CandidateSet[]>([])
const candidateSetId = ref('')
const inlineText = ref('')
const inlineParsed = computed(() => parseInlineSmiles(inlineText.value))
const preuploadedLigandFileId = ref('')
const preuploadedLigandFilename = ref('')
const targetOptions = computed(() => targets.value.map(item => ({ label: item.name, value: item.id })))
const proteinOptions = computed(() => proteins.value.map(item => ({ label: item.name, value: item.id })))
const structureOptions = computed(() => structures.value.filter(item => Boolean(item.prepared_file_id || item.structure_file_id)).map(item => ({ label: structureOptionLabel(item), value: item.id })))
const selectedStructure = computed(() => structures.value.find(item => item.id === selectedStructureId.value) ?? null)
const selectedStructureFileId = computed(() => selectedStructure.value?.prepared_file_id || selectedStructure.value?.structure_file_id || '')
const candidateSetOptions = computed(() => candidateSets.value.map(item => ({ label: `${item.name}（${item.item_count} 个候选物）`, value: item.id })))
const selectedCandidateSet = computed(() => candidateSets.value.find(item => item.id === candidateSetId.value) ?? null)

function handleProjectChange(value: unknown): void {
  const next = typeof value === 'string' ? value : ''
  const query = { ...route.query }
  delete query.file_id
  delete query.filename
  delete query.candidate_set_id
  if (next) query.project_id = next
  else delete query.project_id
  if (next !== projectId.value) {
    preuploadedLigandFileId.value = ''
    preuploadedLigandFilename.value = ''
    candidateSetId.value = ''
    ligandSource.value = 'upload'
    appliedHandoffKey = `${String(query.candidate_set_id ?? '')}|${String(query.file_id ?? '')}|${String(
      query.filename ?? ''
    )}|${next}`
  }
  void router.replace({ query })
}

async function loadProjects(): Promise<void> {
  try {
    projects.value = (await listProjects()).data.items
  } catch {
    projects.value = []
  }
}

async function loadTargets(): Promise<void> {
  const parent = projectId.value; const seq = requestTrackers.targets.next()
  if (!parent) { targets.value = []; return }
  try { const response = await listTargets(parent, { page: 1, page_size: 100 }); if (requestTrackers.targets.isCurrent(seq) && projectId.value === parent) targets.value = response.data.items ?? [] }
  catch { if (requestTrackers.targets.isCurrent(seq) && projectId.value === parent) targets.value = [] }
}

async function loadCandidateSets(): Promise<void> {
  const parent = projectId.value; const seq = requestTrackers.candidateSets.next()
  if (!parent) { candidateSets.value = []; return }
  try { const response = await listCandidateSets(parent, { page: 1, page_size: 100 }); if (requestTrackers.candidateSets.isCurrent(seq) && projectId.value === parent) candidateSets.value = response.data.items ?? [] }
  catch { if (requestTrackers.candidateSets.isCurrent(seq) && projectId.value === parent) candidateSets.value = [] }
}

watch(
  projectId,
  (id, oldId) => {
    if (oldId && id !== oldId) {
      preuploadedLigandFileId.value = ''
      preuploadedLigandFilename.value = ''
      candidateSetId.value = ''
      ligandSource.value = 'upload'
      appliedHandoffKey = getHandoffKey()
    }
    selectedTargetId.value = ''
    selectedProteinId.value = ''
    selectedStructureId.value = ''
    candidateSetId.value = ''
    proteins.value = []
    structures.value = []
    void loadTargets()
    void loadCandidateSets()
  },
  { immediate: true }
)

watch(selectedTargetId, async id => {
  const seq = requestTrackers.proteins.next()
  pocketFile.value = null
  pocketName.value = ''
  selectedProteinId.value = ''
  selectedStructureId.value = ''
  proteins.value = []
  structures.value = []
  if (!id) return
  try { const response = await getTarget(id); if (requestTrackers.proteins.isCurrent(seq) && selectedTargetId.value === id) proteins.value = response.data.proteins ?? [] }
  catch { if (requestTrackers.proteins.isCurrent(seq) && selectedTargetId.value === id) proteins.value = [] }
})

watch(selectedProteinId, async id => {
  const seq = requestTrackers.structures.next()
  pocketFile.value = null
  pocketName.value = ''
  selectedStructureId.value = ''
  structures.value = []
  if (!id) return
  try { const response = await listStructures(id); if (requestTrackers.structures.isCurrent(seq) && selectedProteinId.value === id) structures.value = response.data.items ?? [] }
  catch { if (requestTrackers.structures.isCurrent(seq) && selectedProteinId.value === id) structures.value = [] }
})



watch(candidateSetId, () => { if (ligandSource.value === 'candidate') countedLigands.value = selectedCandidateSet.value?.item_count ?? 0 })

watch(ligandSource, source => {
  if (source !== 'upload') clearLigands()
  if (source !== 'candidate') candidateSetId.value = ''
  if (source !== 'inline') inlineText.value = ''
  preuploadedLigandFileId.value = ''
  preuploadedLigandFilename.value = ''
})

let appliedHandoffKey = ''
function getHandoffKey(): string {
  return `${String(route.query.candidate_set_id ?? '')}|${String(route.query.file_id ?? '')}|${String(route.query.filename ?? '')}|${projectId.value}`
}
function applyQueryHandoff(): void {
  const key = getHandoffKey()
  if (key === appliedHandoffKey) return
  appliedHandoffKey = key
  const candidateQuery = route.query.candidate_set_id
  const fileQuery = route.query.file_id
  const filenameQuery = route.query.filename
  if (typeof candidateQuery === 'string' && candidateQuery) {
    ligandSource.value = 'candidate'; candidateSetId.value = candidateQuery
    preuploadedLigandFileId.value = ''; preuploadedLigandFilename.value = ''
  } else if (typeof fileQuery === 'string' && fileQuery) {
    ligandSource.value = 'upload'; preuploadedLigandFileId.value = fileQuery
    preuploadedLigandFilename.value = typeof filenameQuery === 'string' ? filenameQuery : ''
    ligandError.value = ''
  }
}
watch(() => route.query, applyQueryHandoff)
onMounted(() => { applyQueryHandoff(); void loadProjects() })

const receptorFile = ref<File | null>(null)
const receptorName = ref('')
const detectedHetatm = ref<PocketGeometry | null>(null)
const receptorSequence = useRequestSequence()
let parsedReceptorFile: File | null = null

const ligandFiles = ref<File[]>([])
const ligandFormat = ref<'' | 'sdf' | 'csv'>('')
const countedLigands = ref(0)
const countingLigands = ref(false)
const ligandCount = computed(() => ligandSource.value === 'inline' ? inlineParsed.value.validRows.length : ligandSource.value === 'candidate' ? (selectedCandidateSet.value?.item_count ?? 0) : countedLigands.value)
const ligandError = ref('')
const pocketFile = ref<File | null>(null)
const pocketName = ref('')

// LDDM 口袋对接与局部对接状态
const dockLigandFile = ref<File | null>(null)
const dockLigandUpload = ref<File | null>(null)
const dockLigandMolecule = ref<FragmentMolecule | null>(null)
const dockLigandAtomCount = ref<number | null>(null)
const dockLigandCentroid = ref<{ x: number; y: number; z: number } | null>(null)
const dockLigandParsing = ref(false)
const dockLigandError = ref('')
const dockAtomsToDock = ref('')
const dockSketchOpen = ref(false)
const dockLigandSequence = useRequestSequence()
let parsedDockLigandFile: File | null = null

const dockPocketPanelRef = ref<InstanceType<typeof PocketCoordinatePanel> | null>(null)
const dockPocketMode = ref<PocketDefineMode>('ref_ligand')
const dockPocketState = ref<PocketCoordinateState>({
  mode: 'ref_ligand',
  center: null,
  boxSize: null,
  label: '-',
  parsing: false,
  hasAnyInput: false,
  refLigandFile: null,
  refLigandUpload: null,
  pocketFile: null
})
const dockPocketTestIds: PocketTestIds = {
  modeGroup: 'screen-dock-pocket-mode',
  modeRefLigand: 'screen-dock-pocket-ref-ligand',
  modeCoords: 'screen-dock-pocket-coords',
  modeFile: 'screen-dock-pocket-file',
  panel: 'screen-dock-pocket-panel',
  refLigandUpload: 'screen-dock-ref-ligand-upload',
  refLigandName: 'screen-dock-ref-ligand-name',
  refLigandSummary: 'screen-dock-ref-ligand-summary',
  centerX: 'screen-dock-center-x',
  centerY: 'screen-dock-center-y',
  centerZ: 'screen-dock-center-z',
  pocketUpload: 'screen-dock-pocket-upload'
}

const dockAtomsParsed = computed(() =>
  parseAtomIndices(dockAtomsToDock.value.trim(), dockLigandAtomCount.value)
)
const dockAtomsInvalid = computed(() =>
  Boolean(dockAtomsToDock.value.trim()) && !dockAtomsParsed.value.valid
)
const dockActiveCenter = computed(() => dockPocketState.value.center)
const dockCenterReady = computed(() => Boolean(dockActiveCenter.value))

const LDDM_DOCK_PRIMARY_KEYS = ['n_samples']
const LDDM_DOCK_HIDDEN_KEYS = ['generation_mode', 'atoms_to_dock', 'molecule_size', 'center_x', 'center_y', 'center_z']
const lddmSchema = computed(() => (isLddmDock.value ? selectedOption?.value?.parameterSchema ?? null : null))
const lddmParams = ref<ParameterValues>({})
const lddmHiddenParams: Record<string, ParameterFieldOverride> = {
  generation_mode: { hidden: true },
  atoms_to_dock: { hidden: true },
  molecule_size: { hidden: true },
  center_x: { hidden: true },
  center_y: { hidden: true },
  center_z: { hidden: true }
}
const lddmEffectiveParams = computed<ParameterValues>(() => ({
  ...lddmParams.value,
  generation_mode: 'dock',
  ...(dockAtomsToDock.value.trim() ? { atoms_to_dock: dockAtomsToDock.value.trim() } : {})
}))
const lddmParameterErrors = computed(() =>
  isLddmDock.value ? validateParameters(lddmSchema.value, lddmEffectiveParams.value) : []
)

watch(
  lddmSchema,
  schema => {
    if (!schema) return
    lddmParams.value = buildDefaultValues(schema, { omit: LDDM_DOCK_HIDDEN_KEYS })
  },
  { immediate: true }
)

const params = reactive<ScreeningParams>({ ...SCREENING_PARAM_DEFAULTS })
const submitting = ref(false)
const formError = ref('')

const canSubmit = computed(() => {
  if (submitting.value) return false
  const usesProjectAssets =
    receptorSource.value === 'project' || (!isLddmDock.value && ligandSource.value === 'candidate')
  if (usesProjectAssets && !projectId.value) return false
  const receptorReady =
    receptorSource.value === 'project'
      ? Boolean(selectedStructureFileId.value)
      : Boolean(receptorFile.value)
  if (!receptorReady) return false
  if (isLddmDock.value) {
    if (dockLigandParsing.value || dockPocketState.value.parsing) return false
    const hasDockLigand = Boolean(dockLigandUpload.value || preuploadedLigandFileId.value)
    return (
      hasDockLigand &&
      !dockAtomsInvalid.value &&
      dockCenterReady.value &&
      lddmParameterErrors.value.length === 0
    )
  }
  if (ligandSource.value === 'inline') return Boolean(inlineParsed.value.validRows.length)
  if (ligandSource.value === 'candidate') return Boolean(candidateSetId.value && selectedCandidateSet.value)
  if (preuploadedLigandFileId.value) return !ligandError.value
  return !countingLigands.value && ligandFiles.value.length > 0 && !ligandError.value && ligandCount.value > 0
})

function fileStem(name: string): string {
  return name.replace(/\.[^.]+$/, '')
}

async function handleReceptorUpload(file: File): Promise<boolean> {
  const seq = receptorSequence.next()
  receptorFile.value = file
  receptorName.value = file.name
  parsedReceptorFile = file
  detectedHetatm.value = null
  const lower = file.name.toLowerCase()
  if (!lower.endsWith('.pdb') && !lower.endsWith('.ent')) return false
  try {
    const text = await file.text()
    if (!receptorSequence.isCurrent(seq) || parsedReceptorFile !== file || receptorFile.value !== file) {
      return false
    }
    detectedHetatm.value = extractProteinHetatmPocketGeometry(text)
  } catch {
    // 共晶配体探测失败不影响受体上传。
  }
  return false
}

function handlePocketUpload(file: File): boolean {
  pocketFile.value = file
  pocketName.value = file.name
  return false
}

async function handleDockLigandUpload(file: File): Promise<boolean> {
  const seq = dockLigandSequence.next()
  dockLigandFile.value = file
  parsedDockLigandFile = file
  dockLigandUpload.value = null
  dockLigandMolecule.value = null
  dockLigandAtomCount.value = null
  dockLigandCentroid.value = null
  dockLigandError.value = ''
  dockAtomsToDock.value = ''
  dockLigandParsing.value = true
  try {
    const text = await file.text()
    if (!dockLigandSequence.isCurrent(seq) || parsedDockLigandFile !== file || dockLigandFile.value !== file) {
      return false
    }
    const prepared = await parseAndNormalizeLigandUpload(file, text, { convertNonSdfToSdf: false })
    if (!dockLigandSequence.isCurrent(seq) || parsedDockLigandFile !== file || dockLigandFile.value !== file) {
      return false
    }
    if (!prepared) {
      dockLigandError.value = t('screening.config.dockLigandUnreadable')
      return false
    }
    dockLigandUpload.value = prepared.uploadFile
    dockLigandMolecule.value = prepared.molecule
    dockLigandAtomCount.value = prepared.atomCount
    dockLigandCentroid.value = parseReferenceLigandGeometry(text, file.name)?.center ?? null
  } catch {
    if (dockLigandSequence.isCurrent(seq) && parsedDockLigandFile === file) {
      dockLigandError.value = t('screening.config.dockLigandUnreadable')
    }
  } finally {
    if (dockLigandSequence.isCurrent(seq) && parsedDockLigandFile === file) {
      dockLigandParsing.value = false
    }
  }
  return false
}

function handleDockSketchConfirm(payload: { selectedIndices: number[]; exportedFile: File | null }): void {
  dockAtomsToDock.value = formatAtomIndices(payload.selectedIndices)
}

function handleDockPocketStateChange(state: PocketCoordinateState): void {
  dockPocketState.value = state
}

function applyCenterToCoords(center: { x: number; y: number; z: number }, noticeKey: string): void {
  dockPocketPanelRef.value?.setCoordinates(center)
  message.success(t(noticeKey))
}

function detectFormat(name: string): 'sdf' | 'csv' | '' {
  const lower = name.toLowerCase()
  if (lower.endsWith('.csv')) return 'csv'
  if (lower.endsWith('.sdf') || lower.endsWith('.mol')) return 'sdf'
  return ''
}

async function handleLigandUpload(file: File): Promise<boolean> {
  const format = detectFormat(file.name)
  if (!format) { ligandError.value = t('screening.config.onlySdfOrCsv'); return false }
  if (ligandFormat.value && ligandFormat.value !== format) { ligandError.value = t('screening.config.mixedLigandFormats'); return false }
  ligandFormat.value = format
  ligandFiles.value = [...ligandFiles.value, file]
  countedLigands.value = 0
  countingLigands.value = true
  preuploadedLigandFileId.value = ''
  preuploadedLigandFilename.value = ''
  ligandError.value = ''
  const seq = requestTrackers.ligandCount.next()
  try { const count = await countLigands([...ligandFiles.value], format); if (requestTrackers.ligandCount.isCurrent(seq)) { countedLigands.value = count; countingLigands.value = false } }
  catch { if (requestTrackers.ligandCount.isCurrent(seq)) { countedLigands.value = 0; countingLigands.value = false; ligandError.value = t('screening.config.ligandsUnreadable') } }
  return false
}

function clearLigands(): void {
  requestTrackers.ligandCount.invalidate()
  countingLigands.value = false
  ligandFiles.value = []
  ligandFormat.value = ''
  countedLigands.value = 0
  ligandError.value = ''
  preuploadedLigandFileId.value = ''
  preuploadedLigandFilename.value = ''
}

async function countLigands(files: File[], format: 'sdf' | 'csv'): Promise<number> {
  if (format === 'csv') {
    let total = 0
    for (const file of files) total += parseCsv(await file.text()).rows.length
    return total
  }
  let total = 0
  for (const file of files) total += rewriteSdfRecordsWithTitle(await file.text(), fileStem(file.name)).length
  return total
}

async function buildSdfPayload(files: File[]): Promise<File> {
  const blocks: string[] = []
  for (const file of files) blocks.push(...rewriteSdfRecordsWithTitle(await file.text(), fileStem(file.name)))
  return new File([blocks.join('\n')], 'ligands.sdf', { type: 'chemical/x-mdl-sdfile' })
}

function parseCsv(text: string): { headers: string[]; rows: string[][] } {
  const source = text.replace(/^\uFEFF/, '')
  const rows: string[][] = []; let row: string[] = []; let field = ''; let quoted = false
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i]
    if (quoted) {
      if (char === '"' && source[i + 1] === '"') { field += '"'; i += 1 }
      else if (char === '"') quoted = false
      else field += char
    } else if (char === '"' && field.length === 0) quoted = true
    else if (char === ',') { row.push(field); field = '' }
    else if (char === '\n') { row.push(field); if (row.some(cell => cell.trim())) rows.push(row); row = []; field = '' }
    else if (char !== '\r') field += char
  }
  row.push(field); if (row.some(cell => cell.trim())) rows.push(row)
  return { headers: (rows.shift() ?? []).map(header => header.trim()), rows }
}

async function buildCsvPayload(files: File[]): Promise<File> {
  const output = ['molecule_id,SMILES']
  for (const file of files) {
    const { headers, rows } = parseCsv(await file.text())
    const smilesIndex = headers.findIndex(header => header.toLowerCase().includes('smiles'))
    if (smilesIndex < 0) throw new Error(t('screening.config.csvMissingSmiles'))
    const idIndex = headers.findIndex(header => ['molecule_id', 'ligand_id', 'name', 'id'].includes(header.toLowerCase()))
    const stem = fileStem(file.name)
    rows.forEach((cells, index) => {
      const smiles = (cells[smilesIndex] ?? '').trim(); if (!smiles) return
      const id = (cells[idIndex] ?? '').trim() || (rows.length === 1 ? stem : `${stem}_${index + 1}`)
      output.push(`${escapeCsvCell(id)},${escapeCsvCell(smiles)}`)
    })
  }
  return new File([output.join('\n')], 'ligands.csv', { type: 'text/csv' })
}

async function handleSubmit(): Promise<void> {
  formError.value = ''
  if (isLddmDock.value) {
    if (receptorSource.value === 'project') {
      if (!projectId.value) { formError.value = t('screening.config.needProject'); return }
      if (!selectedStructureFileId.value) { formError.value = t('screening.config.needStructure'); return }
    } else if (!receptorFile.value) {
      formError.value = t('screening.config.needReceptor')
      return
    }
    const ligandIdFallback = preuploadedLigandFileId.value
    if (!dockLigandUpload.value && !ligandIdFallback) {
      formError.value = t('screening.config.dockNeedLigand')
      return
    }
    if (dockAtomsInvalid.value) {
      formError.value = t('design.molecule.atomsToDockInvalid')
      return
    }
    if (!dockActiveCenter.value) {
      formError.value = t('screening.config.dockNeedPocketCenter')
      return
    }
    if (lddmParameterErrors.value.length > 0) {
      formError.value = t('design.molecule.invalidNum')
      return
    }

    const center = dockActiveCenter.value
    const supportsRefLigand = Boolean(selectedOption?.value?.inputSlots?.includes('ref_ligand'))
    const trimmedAtoms = dockAtomsToDock.value.trim()
    submitting.value = true
    try {
      const uploads: Record<string, string> = {}
      uploads.protein_pdb =
        receptorSource.value === 'project'
          ? selectedStructureFileId.value
          : (await uploadFile(receptorFile.value as File)).data.id
      uploads.fragment_sdf = dockLigandUpload.value
        ? (await uploadFile(dockLigandUpload.value)).data.id
        : ligandIdFallback
      const refLigandUpload = dockPocketState.value.refLigandUpload
      if (dockPocketState.value.mode === 'ref_ligand' && refLigandUpload && supportsRefLigand) {
        uploads.ref_ligand = (await uploadFile(refLigandUpload)).data.id
      }

      const task = await submitToolTask({
        toolSlug: selectedSlug.value,
        projectId: projectId.value || undefined,
        name: `LDDM 口袋对接 ${new Date().toISOString().slice(0, 10)}`,
        params: {
          ...normalizeParameters(lddmSchema.value, lddmEffectiveParams.value),
          generation_mode: 'dock',
          ...(trimmedAtoms ? { atoms_to_dock: trimmedAtoms } : {}),
          center_x: center.x,
          center_y: center.y,
          center_z: center.z
        },
        standardInputUploads: uploads
      })
      message.success(t('screening.config.success'))
      await router.push(`/tasks/${task.id}/results`)
    } catch (error) {
      formError.value = error instanceof Error ? error.message : t('screening.config.submitFailed')
    } finally {
      submitting.value = false
    }
    return
  }

  const snapshot = {
    receptorSource: receptorSource.value,
    receptorFile: receptorFile.value,
    receptorFileId: selectedStructureFileId.value,
    projectId: projectId.value,
    ligandSource: ligandSource.value,
    candidateSetId: candidateSetId.value,
    preuploadedFileId: preuploadedLigandFileId.value,
    files: [...ligandFiles.value],
    format: ligandFormat.value,
    inlineRows: [...inlineParsed.value.validRows],
    pocketFile: pocketFile.value,
    slug: selectedSlug.value,
    params: { ...params }
  }
  if (snapshot.receptorSource === 'project') {
    if (!snapshot.projectId) { formError.value = t('screening.config.needProject'); return }
    if (!snapshot.receptorFileId) { formError.value = t('screening.config.needStructure'); return }
  } else if (!snapshot.receptorFile) { formError.value = t('screening.config.needReceptor'); return }
  if (snapshot.ligandSource === 'candidate') {
    if (!snapshot.projectId) { formError.value = t('screening.config.needProject'); return }
    if (!snapshot.candidateSetId) { formError.value = t('screening.config.needCandidateSet'); return }
  } else if (snapshot.ligandSource === 'inline') {
    if (!snapshot.inlineRows.length) { formError.value = t('screening.config.inlineSmilesEmpty'); return }
  } else {
    if (!snapshot.files.length && !snapshot.preuploadedFileId) { formError.value = t('screening.config.needLigands'); return }
    if (countingLigands.value || ligandError.value || (!snapshot.preuploadedFileId && ligandCount.value <= 0)) { formError.value = ligandError.value || t('screening.config.needLigands'); return }
  }
  submitting.value = true
  try {
    const uploads: Record<string, string> = {}
    if (snapshot.receptorSource === 'project') uploads.protein_pdb = snapshot.receptorFileId
    else uploads.protein_pdb = (await uploadFile(snapshot.receptorFile as File)).data.id
    if (snapshot.ligandSource === 'candidate') {
      const exported = await exportCandidateSet(snapshot.candidateSetId)
      if (!exported.data.file_id) throw new Error(t('screening.config.candidateSetExportFailed'))
      uploads.ligand_smiles = exported.data.file_id
    } else if (snapshot.preuploadedFileId) uploads.ligand_smiles = snapshot.preuploadedFileId
    else if (snapshot.ligandSource === 'inline') uploads.ligand_smiles = (await uploadFile(buildInlineSmilesFile(snapshot.inlineRows, 'inline_smiles.csv'))).data.id
    else if (snapshot.format === 'csv') uploads.ligand_smiles = (await uploadFile(await buildCsvPayload(snapshot.files))).data.id
    else uploads.ligand_sdf = (await uploadFile(await buildSdfPayload(snapshot.files))).data.id
    if (snapshot.pocketFile) uploads.binding_pocket = (await uploadFile(snapshot.pocketFile)).data.id
    const task = await submitToolTask({ toolSlug: snapshot.slug, projectId: snapshot.projectId || undefined, name: `虚拟筛选 ${new Date().toISOString().slice(0, 10)}`, params: snapshot.params, standardInputUploads: uploads })
    message.success(t('screening.config.success'))
    await router.push(`/tasks/${task.id}/screening`)
  } catch (error) {
    formError.value = error instanceof Error ? error.message : t('screening.config.submitFailed')
  } finally { submitting.value = false }
}

const paramFields = computed(() => [
  {
    key: 'pharmacophore_min_features' as const,
    label: t('screening.config.pharmacophoreMinFeatures'),
    step: 1
  },
  {
    key: 'docking_score_cutoff' as const,
    label: t('screening.config.dockingScoreCutoff'),
    step: 0.5
  },
  { key: 'top_n' as const, label: t('screening.config.topN'), step: 1 },
  { key: 'exhaustiveness' as const, label: t('screening.config.exhaustiveness'), step: 1 },
  { key: 'n_poses' as const, label: t('screening.config.nPoses'), step: 1 },
  { key: 'box_size' as const, label: t('screening.config.boxSize'), step: 1 },
  { key: 'seed' as const, label: t('screening.config.seed'), step: 1 }
])
</script>

<template>
  <main class="screen-config" data-testid="screen-config-page">
    <AppPageHeader :title="t('screening.config.title')" :subtitle="t('screening.config.subtitle')" />

    <a-card
      v-if="!projectIdOverride"
      :title="t('screening.config.project')"
      data-testid="screen-config-project"
    >
      <a-select
        :value="projectId"
        :options="projectOptions"
        show-search
        option-filter-prop="label"
        :placeholder="t('screening.config.projectPlaceholder')"
        style="width: 100%"
        data-testid="screen-config-project-select"
        @change="handleProjectChange"
      />
      <p class="screen-config__hint">{{ t('screening.config.projectHint') }}</p>
    </a-card>

    <a-card :title="t('design.modelSelect.label')">
      <ModelSelect v-model="selectedSlug" :options="displayModelOptions" :loading="modelLoading" />
    </a-card>

    <a-card :title="t('screening.config.inputs')">
      <a-form layout="vertical">
        <a-form-item :label="t('screening.config.receptor')" required>
          <a-radio-group
            v-model:value="receptorSource"
            button-style="solid"
            data-testid="screen-config-receptor-source"
          >
            <a-radio-button value="upload">
              {{ t('screening.config.sourceUpload') }}
            </a-radio-button>
            <a-radio-button value="project">
              {{ t('screening.config.sourceProject') }}
            </a-radio-button>
          </a-radio-group>

          <template v-if="receptorSource === 'upload'">
            <a-upload
              :before-upload="handleReceptorUpload"
              :max-count="1"
              accept=".pdb,.cif,.ent"
              :file-list="[]"
              data-testid="screen-config-receptor-upload"
            >
              <a-button>{{ t('screening.config.chooseFile') }}</a-button>
            </a-upload>
            <span v-if="receptorName" class="screen-config__file">{{ receptorName }}</span>
            <div v-if="isLddmDock && detectedHetatm" class="screen-config__hetatm" data-testid="screen-dock-hetatm-banner">
              <span>{{ t('design.molecule.hetatmDetected', { count: detectedHetatm.pointCount }) }}</span>
              <a-button
                type="link"
                size="small"
                data-testid="screen-dock-use-hetatm"
                @click="applyCenterToCoords(detectedHetatm.center, 'design.molecule.hetatmApplied')"
              >
                {{ t('design.molecule.useHetatmCenter') }}
              </a-button>
            </div>
          </template>

          <template v-else>
            <div class="screen-config__project-picker">
              <a-select
                v-model:value="selectedTargetId"
                :options="targetOptions"
                :placeholder="t('screening.config.target')"
                show-search
                option-filter-prop="label"
                style="min-width: 200px"
                data-testid="screen-config-target"
              />
              <a-select
                v-model:value="selectedProteinId"
                :options="proteinOptions"
                :placeholder="t('screening.config.protein')"
                :disabled="!selectedTargetId"
                show-search
                option-filter-prop="label"
                style="min-width: 200px"
                data-testid="screen-config-protein"
              />
              <a-select
                v-model:value="selectedStructureId"
                :options="structureOptions"
                :placeholder="t('screening.config.structure')"
                :disabled="!selectedProteinId"
                show-search
                option-filter-prop="label"
                style="min-width: 280px"
                data-testid="screen-config-structure"
              />
            </div>
            <p v-if="!targets.length" class="screen-config__hint">
              {{ t('screening.config.noTargets') }}
            </p>
            <p v-else-if="selectedTargetId && !structures.length" class="screen-config__hint">
              {{ t('screening.config.noStructures') }}
            </p>
            <p v-else-if="selectedStructureFileId" class="screen-config__hint">
              {{ t('screening.config.structureSelected') }}
            </p>
          </template>
        </a-form-item>

        <a-form-item v-if="!isLddmDock" :label="t('screening.config.ligandLibrary')" required>
          <a-radio-group
            v-model:value="ligandSource"
            button-style="solid"
            data-testid="screen-config-ligand-source"
          >
            <a-radio-button value="upload">
              {{ t('screening.config.sourceUpload') }}
            </a-radio-button>
            <a-radio-button value="candidate">
              {{ t('screening.config.sourceCandidate') }}
            </a-radio-button>
            <a-radio-button value="inline">
              {{ t('screening.config.sourceInline') }}
            </a-radio-button>
          </a-radio-group>

          <template v-if="ligandSource === 'candidate'">
            <a-select
              v-model:value="candidateSetId"
              :options="candidateSetOptions"
              :placeholder="t('screening.config.candidateSet')"
              :disabled="!projectId"
              show-search
              option-filter-prop="label"
              style="width: 100%; margin-top: 12px"
              data-testid="screen-config-candidate-set"
            />
            <p class="screen-config__hint">
              {{ t('screening.config.candidateSetHint') }}
            </p>
            <p v-if="!candidateSets.length" class="screen-config__hint">
              {{ t('screening.config.noCandidateSets') }}
            </p>
          </template>

          <template v-else-if="ligandSource === 'inline'">
            <a-textarea v-model:value="inlineText" :rows="6" :placeholder="t('screening.config.inlineSmilesPlaceholder')" data-testid="screen-config-inline-smiles" />
            <p class="screen-config__hint">{{ t('screening.config.inlineSmilesSummary', { valid: inlineParsed.validRows.length, total: inlineParsed.totalNonEmptyLines, skipped: inlineParsed.skippedCount }) }}</p>
            <div class="screen-config__files" data-testid="screen-config-inline-preview">
              <div v-for="(row, index) in inlineParsed.previewRows" :key="`${row.smiles}-${index}`">
                <Smiles2DCell :smiles="row.smiles" :width="120" :height="76" />
                <code>{{ row.smiles }}</code>
              </div>
            </div>
            <a-alert v-if="inlineText && !inlineParsed.validRows.length" type="warning" show-icon :message="t('screening.config.inlineSmilesEmpty')" />
          </template>
          <template v-else>
          <a-upload
            :before-upload="handleLigandUpload"
            multiple
            accept=".sdf,.mol,.csv"
            :file-list="[]"
            data-testid="screen-config-ligands-upload"
          >
            <a-button>{{ t('screening.config.chooseFiles') }}</a-button>
          </a-upload>
          <a-button
            v-if="ligandFiles.length || preuploadedLigandFileId"
            type="link"
            size="small"
            @click="clearLigands"
          >
            {{ t('screening.config.clearLigands') }}
          </a-button>
          <p class="screen-config__hint">{{ t('screening.config.ligandLibraryHint') }}</p>
          <div
            v-if="preuploadedLigandFileId"
            class="screen-config__files"
            data-testid="screen-config-preuploaded-ligands"
          >
            <a-tag color="blue">
              {{ preuploadedLigandFilename || preuploadedLigandFileId }}
            </a-tag>
            <span class="screen-config__hint">{{ t('screening.config.preuploadedLigands') }}</span>
          </div>
          <div v-if="ligandFiles.length" class="screen-config__files" data-testid="screen-config-ligand-files">
            <a-tag v-for="file in ligandFiles" :key="file.name">{{ file.name }}</a-tag>
            <span class="screen-config__hint">{{ t('screening.config.ligandCountValue', { count: ligandCount }) }}</span>
          </div>
          <a-alert v-if="ligandError" type="warning" show-icon :message="ligandError" />
          </template>
        </a-form-item>

        <template v-else>
          <a-form-item :label="t('screening.config.dockLigandTitle')" required data-testid="screen-dock-ligand-section">
            <div class="screen-config__files">
              <a-upload
                :before-upload="handleDockLigandUpload"
                :max-count="1"
                accept=".sdf,.sd,.mol,.mol2,.pdb"
                :file-list="[]"
                data-testid="screen-dock-ligand-upload"
              >
                <a-button>{{ t('screening.config.chooseFile') }}</a-button>
              </a-upload>
              <span v-if="dockLigandFile" class="screen-config__file" data-testid="screen-dock-ligand-name">
                {{ dockLigandFile.name }}
              </span>
              <a-button
                v-if="dockLigandCentroid"
                type="link"
                size="small"
                data-testid="screen-dock-use-ligand-center"
                @click="applyCenterToCoords(dockLigandCentroid, 'screening.config.dockLigandCenterApplied')"
              >
                {{ t('screening.config.dockUseLigandCenter') }}
              </a-button>
            </div>
            <p class="screen-config__hint">{{ t('screening.config.dockLigandHint') }}</p>
            <div v-if="dockLigandFile && !dockLigandParsing && dockLigandAtomCount !== null" class="screen-config__hint">
              {{ t('design.molecule.fragmentAtomCount', { count: dockLigandAtomCount, lastIndex: dockLigandAtomCount - 1 }) }}
            </div>
            <MoleculeInlineFragmentCard
              v-if="dockLigandMolecule && !dockLigandParsing"
              class="screen-config__sketch-card"
              :filename="dockLigandFile?.name || dockLigandMolecule.name"
              :atoms="dockLigandMolecule.atoms"
              :bonds="dockLigandMolecule.bonds"
              :selected-indices="dockAtomsParsed.valid ? dockAtomsParsed.indices : []"
              mode="dock"
              :disabled="submitting"
              @open-sketch="dockSketchOpen = true"
            />
            <a-alert v-if="dockLigandError" type="warning" show-icon :message="dockLigandError" />
            <div class="screen-config__atoms-field">
              <label class="screen-config__atoms-label" for="screen-dock-atoms">{{ t('design.molecule.atomsToDock') }}</label>
              <a-input
                id="screen-dock-atoms"
                v-model:value="dockAtomsToDock"
                :disabled="submitting"
                :status="dockAtomsInvalid ? 'error' : undefined"
                placeholder="0 1 2"
                data-testid="screen-dock-atoms-input"
              />
              <span class="screen-config__hint">
                {{ t(dockAtomsInvalid ? 'design.molecule.atomsToDockInvalid' : 'design.molecule.atomsToDockHint') }}
              </span>
            </div>
          </a-form-item>

          <a-form-item :label="t('design.molecule.pocketDefineMode')" required data-testid="screen-dock-pocket-section">
            <PocketCoordinatePanel
              ref="dockPocketPanelRef"
              v-model="dockPocketMode"
              :disabled="submitting"
              :test-ids="dockPocketTestIds"
              @change="handleDockPocketStateChange"
            />
          </a-form-item>
        </template>

        <a-form-item v-if="!isLddmDock" :label="t('screening.config.pocket')">
          <a-upload :before-upload="handlePocketUpload" :max-count="1" accept=".pdb" :file-list="[]">
            <a-button>{{ t('screening.config.chooseFile') }}</a-button>
          </a-upload>
          <span v-if="pocketName" class="screen-config__file">{{ pocketName }}</span>
          <p class="screen-config__hint">{{ t('screening.config.pocketHint') }}</p>
        </a-form-item>
      </a-form>
    </a-card>

    <a-row v-if="!isLddmDock" :gutter="16">
      <a-col :xs="24" :lg="12">
        <a-card :title="t('screening.config.params')">
          <a-form layout="vertical">
            <a-row :gutter="12">
              <a-col v-for="field in paramFields" :key="field.key" :xs="24" :sm="12">
                <a-form-item :label="field.label">
                  <a-input-number
                    v-model:value="params[field.key]"
                    :min="SCREENING_PARAM_RANGES[field.key].min"
                    :max="SCREENING_PARAM_RANGES[field.key].max"
                    :step="field.step"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </a-form>
        </a-card>
      </a-col>

      <a-col :xs="24" :lg="12">
        <a-card :title="t('screening.config.rulesTitle')" data-testid="screen-config-rules">
          <p class="screen-config__hint">{{ t('screening.config.rulesHint') }}</p>
          <ol class="screen-config__rules">
            <li>
              <strong>{{ t('screening.config.ruleInput') }}</strong>
              <span v-if="preuploadedLigandFileId && ligandCount === 0">{{ t('screening.config.preuploadedLigands') }}</span>
              <span v-else>{{ t('screening.config.ruleInputHint', { count: ligandCount }) }}</span>
            </li>
            <li>
              <strong>{{ t('screening.config.rulePharmacophore') }}</strong>
              <span>{{ t('screening.config.rulePharmacophoreHint', { count: params.pharmacophore_min_features }) }}</span>
            </li>
            <li>
              <strong>{{ t('screening.config.ruleDocking') }}</strong>
              <span>{{ t('screening.config.ruleDockingHint', { count: params.exhaustiveness, poses: params.n_poses }) }}</span>
            </li>
            <li>
              <strong>{{ t('screening.config.ruleCutoff') }}</strong>
              <span>{{ t('screening.config.ruleCutoffHint', { score: params.docking_score_cutoff }) }}</span>
            </li>
            <li>
              <strong>{{ t('screening.config.ruleKept') }}</strong>
              <span>{{ t('screening.config.ruleKeptHint', { count: params.top_n }) }}</span>
            </li>
          </ol>
          <p class="screen-config__hint">{{ t('screening.config.resultFunnelHint') }}</p>
        </a-card>
      </a-col>
    </a-row>

    <a-row v-else :gutter="16">
      <a-col :xs="24" :lg="12">
        <a-card :title="t('screening.config.params')">
          <ModelParameterForm
            v-if="lddmSchema"
            v-model="lddmParams"
            :schema="lddmSchema"
            :overrides="lddmHiddenParams"
            :primary-keys="LDDM_DOCK_PRIMARY_KEYS"
            :disabled="submitting"
          />
        </a-card>
      </a-col>

      <a-col :xs="24" :lg="12">
        <a-card :title="t('screening.config.dockSummaryTitle')" data-testid="screen-dock-summary">
          <p class="screen-config__hint">{{ t('screening.config.dockSummaryHint') }}</p>
          <ol class="screen-config__rules">
            <li>
              <strong>{{ t('screening.config.dockModeSummary') }}</strong>
              <span>
                {{
                  dockAtomsParsed.valid && dockAtomsParsed.indices.length > 0
                    ? t('screening.config.dockSummaryPartial', { count: dockAtomsParsed.indices.length })
                    : t('screening.config.dockSummaryFull')
                }}
              </span>
            </li>
            <li>
              <strong>{{ t('design.molecule.pocketCenter') }}</strong>
              <span>
                {{
                  dockActiveCenter
                    ? `${dockActiveCenter.x.toFixed(2)}, ${dockActiveCenter.y.toFixed(2)}, ${dockActiveCenter.z.toFixed(2)} Å`
                    : '-'
                }}
              </span>
            </li>
          </ol>
        </a-card>
      </a-col>
    </a-row>

    <div class="screen-config__footer">
      <a-alert v-if="formError" type="error" show-icon :message="formError" data-testid="screen-config-error" />
      <a-button
        type="primary"
        size="large"
        :loading="submitting"
        :disabled="!canSubmit"
        data-testid="screen-config-submit"
        @click="handleSubmit"
      >
        {{
          submitting
            ? t('screening.config.submitting')
            : isLddmDock
              ? t('screening.config.submitLddmDock')
              : t('screening.config.submit')
        }}
      </a-button>
    </div>

    <FragmentSketchModal
      v-if="isLddmDock"
      v-model:open="dockSketchOpen"
      :molecule="dockLigandMolecule"
      :selected-indices="dockAtomsParsed.valid ? dockAtomsParsed.indices : []"
      mode="dock"
      @confirm="handleDockSketchConfirm"
    />
  </main>
</template>

<style scoped lang="less">
.screen-config {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
}

.screen-config__file {
  margin-left: 12px;
  font-weight: 600;
}

.screen-config__project-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
}

.screen-config__files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}

.screen-config__hint {
  margin: 8px 0 0;
  color: var(--ant-color-text-secondary, var(--theme-text-secondary));
}

.screen-config__rules {
  margin: 8px 0 0;
  padding-left: 22px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.screen-config__rules li {
  line-height: 1.6;
}

.screen-config__rules strong {
  display: block;
}

.screen-config__rules span {
  color: var(--ant-color-text-secondary, var(--theme-text-secondary));
}

.screen-config__footer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: flex-start;
}

.screen-config__hetatm,
.screen-config__atoms-field,
.screen-config__sketch-card {
  margin-top: 12px;
}

.screen-config__hetatm {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.screen-config__atoms-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.screen-config__atoms-label {
  font-weight: 500;
}
</style>
