<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import { uploadFile } from '@/api/files'
import { submitToolTask } from '@/api/screening'
import ModelSelect from '@/components/design/ModelSelect.vue'
import { useModelOptions } from '@/composables/useModelOptions'
import { SCREENING_PARAM_DEFAULTS, SCREENING_PARAM_RANGES, VINA_TOOL_SLUG } from '@/types/screening'
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

const props = withDefaults(defineProps<{ projectIdOverride?: string }>(), { projectIdOverride: '' })
const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { options: modelOptions, selectedSlug, loading: modelLoading, load: loadModels } = useModelOptions('docking', { defaultSlug: VINA_TOOL_SLUG })
void loadModels()

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
const ligandFiles = ref<File[]>([])
const ligandFormat = ref<'' | 'sdf' | 'csv'>('')
const countedLigands = ref(0)
const countingLigands = ref(false)
const ligandCount = computed(() => ligandSource.value === 'inline' ? inlineParsed.value.validRows.length : ligandSource.value === 'candidate' ? (selectedCandidateSet.value?.item_count ?? 0) : countedLigands.value)
const ligandError = ref('')
const pocketFile = ref<File | null>(null)
const pocketName = ref('')

const params = reactive<ScreeningParams>({ ...SCREENING_PARAM_DEFAULTS })
const submitting = ref(false)
const formError = ref('')

const canSubmit = computed(() => {
  if (submitting.value) return false
  const usesProjectAssets =
    receptorSource.value === 'project' || ligandSource.value === 'candidate'
  if (usesProjectAssets && !projectId.value) return false
  const receptorReady =
    receptorSource.value === 'project'
      ? Boolean(selectedStructureFileId.value)
      : Boolean(receptorFile.value)
  if (!receptorReady) return false
  if (ligandSource.value === 'inline') return Boolean(inlineParsed.value.validRows.length)
  if (ligandSource.value === 'candidate') return Boolean(candidateSetId.value && selectedCandidateSet.value)
  if (preuploadedLigandFileId.value) return !ligandError.value
  return !countingLigands.value && ligandFiles.value.length > 0 && !ligandError.value && ligandCount.value > 0
})

function fileStem(name: string): string {
  return name.replace(/\.[^.]+$/, '')
}

function handleReceptorUpload(file: File): boolean {
  receptorFile.value = file
  receptorName.value = file.name
  return false
}

function handlePocketUpload(file: File): boolean {
  pocketFile.value = file
  pocketName.value = file.name
  return false
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
      <ModelSelect v-model="selectedSlug" :options="modelOptions" :loading="modelLoading" />
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
            >
              <a-button>{{ t('screening.config.chooseFile') }}</a-button>
            </a-upload>
            <span v-if="receptorName" class="screen-config__file">{{ receptorName }}</span>
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

        <a-form-item :label="t('screening.config.ligandLibrary')" required>
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

        <a-form-item :label="t('screening.config.pocket')">
          <a-upload :before-upload="handlePocketUpload" :max-count="1" accept=".pdb" :file-list="[]">
            <a-button>{{ t('screening.config.chooseFile') }}</a-button>
          </a-upload>
          <span v-if="pocketName" class="screen-config__file">{{ pocketName }}</span>
          <p class="screen-config__hint">{{ t('screening.config.pocketHint') }}</p>
        </a-form-item>
      </a-form>
    </a-card>

    <a-row :gutter="16">
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
        {{ submitting ? t('screening.config.submitting') : t('screening.config.submit') }}
      </a-button>
    </div>
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
</style>
