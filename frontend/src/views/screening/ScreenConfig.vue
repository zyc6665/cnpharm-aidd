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
import {
  SCREENING_PARAM_DEFAULTS,
  SCREENING_PARAM_RANGES,
  VINA_TOOL_SLUG
} from '@/types/screening'
import type { ScreeningParams } from '@/types/screening'
import { exportCandidateSet, listCandidateSets } from '@/api/compounds'
import { listProjects } from '@/api/projects'
import { getTarget, listStructures, listTargets } from '@/api/targets'
import { structureOptionLabel } from '@/domain/targets/structure-option'
import type { CandidateSet } from '@/types/compounds'
import type { ResearchProject } from '@/types/projects'
import type { ProteinDetail, ProteinStructureDetail, TargetSummary } from '@/types/targets'

const props = withDefaults(defineProps<{ projectIdOverride?: string }>(), {
  projectIdOverride: ''
})

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const {
  options: modelOptions,
  selectedSlug,
  loading: modelLoading,
  load: loadModels
} = useModelOptions('docking', { defaultSlug: VINA_TOOL_SLUG })
void loadModels()

const projectId = computed(() => {
  if (props.projectIdOverride) return props.projectIdOverride
  const raw = route.query.project_id
  if (typeof raw === 'string' && raw) return raw
  const paramId = route.params?.projectId
  return typeof paramId === 'string' ? paramId : ''
})

const projects = ref<ResearchProject[]>([])
const projectOptions = computed(() =>
  projects.value.map(item => ({ label: item.name, value: item.id }))
)

/**
 * 输入来源。项目内的受体结构与候选集已经是落盘资产（`file:<id>`），可以直接当
 * `standard_input_uploads` 的值——不必让用户先导出再上传一遍，URL 里也不会多出
 * 一次几百 KB 的往返。
 */
const receptorSource = ref<'upload' | 'project'>('upload')
const ligandSource = ref<'upload' | 'candidate'>('upload')

const targets = ref<TargetSummary[]>([])
const proteins = ref<ProteinDetail[]>([])
const structures = ref<ProteinStructureDetail[]>([])
const selectedTargetId = ref('')
const selectedProteinId = ref('')
const selectedStructureId = ref('')
const candidateSets = ref<CandidateSet[]>([])
const candidateSetId = ref('')

const targetOptions = computed(() =>
  targets.value.map(item => ({ label: item.name, value: item.id }))
)
const proteinOptions = computed(() =>
  proteins.value.map(item => ({ label: item.name, value: item.id }))
)
/** 只有落过盘的结构才能当输入（物化成 ArtifactVersion 需要真实文件）。 */
const structureOptions = computed(() =>
  structures.value
    .filter(item => Boolean(item.prepared_file_id || item.structure_file_id))
    .map(item => ({ label: structureOptionLabel(item), value: item.id }))
)
const selectedStructure = computed(
  () => structures.value.find(item => item.id === selectedStructureId.value) ?? null
)
const selectedStructureFileId = computed(
  () =>
    selectedStructure.value?.prepared_file_id ||
    selectedStructure.value?.structure_file_id ||
    ''
)
const candidateSetOptions = computed(() =>
  candidateSets.value.map(item => ({
    label: `${item.name}（${item.item_count} 个候选物）`,
    value: item.id
  }))
)
const selectedCandidateSet = computed(
  () => candidateSets.value.find(item => item.id === candidateSetId.value) ?? null
)

function handleProjectChange(value: unknown): void {
  const next = typeof value === 'string' ? value : ''
  void router.replace({ query: { ...route.query, project_id: next || undefined } })
}

async function loadProjects(): Promise<void> {
  try {
    projects.value = (await listProjects()).data.items
  } catch {
    projects.value = []
  }
}

async function loadTargets(): Promise<void> {
  if (!projectId.value) {
    targets.value = []
    return
  }
  try {
    const response = await listTargets(projectId.value, { page: 1, page_size: 100 })
    targets.value = response.data.items ?? []
  } catch {
    targets.value = []
  }
}

async function loadCandidateSets(): Promise<void> {
  if (!projectId.value) {
    candidateSets.value = []
    return
  }
  try {
    const response = await listCandidateSets(projectId.value, { page: 1, page_size: 100 })
    candidateSets.value = response.data.items ?? []
  } catch {
    candidateSets.value = []
  }
}

watch(
  projectId,
  () => {
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
  selectedProteinId.value = ''
  selectedStructureId.value = ''
  structures.value = []
  if (!id) {
    proteins.value = []
    return
  }
  try {
    const response = await getTarget(id)
    proteins.value = response.data.proteins ?? []
  } catch {
    proteins.value = []
  }
})

watch(selectedProteinId, async id => {
  selectedStructureId.value = ''
  if (!id) {
    structures.value = []
    return
  }
  try {
    const response = await listStructures(id)
    structures.value = response.data.items ?? []
  } catch {
    structures.value = []
  }
})

/** 候选集是「已经算好的分子」，选中它就把分子数直接显示到规则卡上。 */
watch(candidateSetId, id => {
  if (ligandSource.value !== 'candidate') return
  const set = candidateSets.value.find(item => item.id === id)
  ligandCount.value = set?.item_count ?? 0
})

watch(ligandSource, source => {
  if (source === 'candidate') {
    clearLigands()
    ligandCount.value = selectedCandidateSet.value?.item_count ?? 0
    return
  }
  candidateSetId.value = ''
  ligandCount.value = 0
})

onMounted(() => {
  void loadProjects()
})

const receptorFile = ref<File | null>(null)
const receptorName = ref('')
const ligandFiles = ref<File[]>([])
const ligandFormat = ref<'' | 'sdf' | 'csv'>('')
const ligandCount = ref(0)
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
  if (ligandSource.value === 'candidate') return Boolean(candidateSetId.value)
  return ligandFiles.value.length > 0 && !ligandError.value && ligandCount.value > 0
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

let ligandCountSeq = 0

async function handleLigandUpload(file: File): Promise<boolean> {
  const format = detectFormat(file.name)
  if (!format) {
    ligandError.value = t('screening.config.onlySdfOrCsv')
    return false
  }
  if (ligandFormat.value && ligandFormat.value !== format) {
    ligandError.value = t('screening.config.mixedLigandFormats')
    return false
  }
  ligandFormat.value = format
  ligandFiles.value = [...ligandFiles.value, file]
  ligandError.value = ''
  const seq = ++ligandCountSeq
  try {
    const count = await countLigands([...ligandFiles.value], format)
    if (seq === ligandCountSeq) ligandCount.value = count
  } catch {
    if (seq === ligandCountSeq) {
      ligandCount.value = 0
      ligandError.value = t('screening.config.ligandsUnreadable')
    }
  }
  return false
}

function clearLigands(): void {
  ligandCountSeq += 1
  ligandFiles.value = []
  ligandFormat.value = ''
  ligandCount.value = 0
  ligandError.value = ''
}

async function countLigands(files: File[], format: 'sdf' | 'csv'): Promise<number> {
  if (format === 'csv') {
    let total = 0
    for (const file of files) {
      total += parseCsv(await file.text()).rows.length
    }
    return total
  }
  let total = 0
  for (const file of files) {
    total += splitSdfRecords(await file.text()).length
  }
  return total
}

function splitSdfRecords(text: string): string[] {
  return text
    .split(/\$\$\$\$\s*/)
    .map(record => record.trim())
    .filter(Boolean)
}

async function buildSdfPayload(): Promise<File> {
  const blocks: string[] = []
  for (const file of ligandFiles.value) {
    const stem = fileStem(file.name)
    const records = splitSdfRecords(await file.text())
    records.forEach((record, index) => {
      const lines = record.split(/\r?\n/)
      lines[0] = records.length === 1 ? stem : `${stem}_${index + 1}`
      blocks.push(`${lines.join('\n')}\n$$$$`)
    })
  }
  return new File([blocks.join('\n')], 'ligands.sdf', { type: 'chemical/x-mdl-sdfile' })
}

function parseCsv(text: string): { headers: string[]; rows: string[][] } {
  const source = text.replace(/^\uFEFF/, '')
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let inQuotes = false
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i]
    if (inQuotes) {
      if (char === '"' && source[i + 1] === '"') {
        field += '"'
        i += 1
      } else if (char === '"') {
        inQuotes = false
      } else {
        field += char
      }
      continue
    }
    if (char === '"') {
      inQuotes = true
    } else if (char === ',') {
      row.push(field)
      field = ''
    } else if (char === '\n') {
      row.push(field)
      if (row.some(cell => cell.trim())) rows.push(row)
      row = []
      field = ''
    } else if (char !== '\r') {
      field += char
    }
  }
  row.push(field)
  if (row.some(cell => cell.trim())) rows.push(row)
  const headers = (rows.shift() ?? []).map(header => header.trim())
  return { headers, rows }
}

async function buildCsvPayload(): Promise<File> {
  const output = ['molecule_id,SMILES']
  for (const file of ligandFiles.value) {
    const { headers, rows } = parseCsv(await file.text())
    const smilesIndex = headers.findIndex(header => header.toLowerCase().includes('smiles'))
    if (smilesIndex < 0) {
      throw new Error(t('screening.config.csvMissingSmiles'))
    }
    const idIndex = headers.findIndex(header =>
      ['molecule_id', 'ligand_id', 'name', 'id'].includes(header.toLowerCase())
    )
    const stem = fileStem(file.name)
    rows.forEach((cells, index) => {
      const smiles = (cells[smilesIndex] ?? '').trim()
      if (!smiles) return
      const rawId = idIndex >= 0 ? (cells[idIndex] ?? '').trim() : ''
      const moleculeId = rawId || (rows.length === 1 ? stem : `${stem}_${index + 1}`)
      output.push(`${moleculeId},${smiles}`)
    })
  }
  return new File([output.join('\n')], 'ligands.csv', { type: 'text/csv' })
}

async function handleSubmit(): Promise<void> {
  formError.value = ''
  if (receptorSource.value === 'project') {
    if (!projectId.value) {
      formError.value = t('screening.config.needProject')
      return
    }
    if (!selectedStructureFileId.value) {
      formError.value = t('screening.config.needStructure')
      return
    }
  } else if (!receptorFile.value) {
    formError.value = t('screening.config.needReceptor')
    return
  }
  if (ligandSource.value === 'candidate') {
    if (!projectId.value) {
      formError.value = t('screening.config.needProject')
      return
    }
    if (!candidateSetId.value) {
      formError.value = t('screening.config.needCandidateSet')
      return
    }
  } else {
    if (!ligandFiles.value.length) {
      formError.value = t('screening.config.needLigands')
      return
    }
    if (ligandError.value || ligandCount.value <= 0) {
      formError.value = ligandError.value || t('screening.config.needLigands')
      return
    }
  }

  submitting.value = true
  try {
    const standardInputUploads: Record<string, string> = {}
    if (receptorSource.value === 'project') {
      standardInputUploads.protein_pdb = selectedStructureFileId.value
    } else {
      const receptor = await uploadFile(receptorFile.value as File)
      standardInputUploads.protein_pdb = receptor.data.id
    }
    if (ligandSource.value === 'candidate') {
      // 候选集导出直接落盘，拿 file_id 当输入：不再「下载一次再上传一次」。
      const exported = await exportCandidateSet(candidateSetId.value)
      const exportedFileId = exported.data.file_id
      if (!exportedFileId) {
        throw new Error(t('screening.config.candidateSetExportFailed'))
      }
      standardInputUploads.ligand_smiles = exportedFileId
    } else if (ligandFormat.value === 'csv') {
      const payload = await buildCsvPayload()
      const uploaded = await uploadFile(payload)
      standardInputUploads.ligand_smiles = uploaded.data.id
    } else {
      const payload = await buildSdfPayload()
      const uploaded = await uploadFile(payload)
      standardInputUploads.ligand_sdf = uploaded.data.id
    }
    if (pocketFile.value) {
      const pocket = await uploadFile(pocketFile.value)
      standardInputUploads.binding_pocket = pocket.data.id
    }
    const task = await submitToolTask({
      toolSlug: selectedSlug.value,
      projectId: projectId.value || undefined,
      name: `虚拟筛选 ${new Date().toISOString().slice(0, 10)}`,
      params: { ...params },
      standardInputUploads
    })
    message.success(t('screening.config.success'))
    await router.push(`/tasks/${task.id}/screening`)
  } catch (error) {
    formError.value = error instanceof Error ? error.message : t('screening.config.submitFailed')
  } finally {
    submitting.value = false
  }
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
          <a-button v-if="ligandFiles.length" type="link" size="small" @click="clearLigands">
            {{ t('screening.config.clearLigands') }}
          </a-button>
          <p class="screen-config__hint">{{ t('screening.config.ligandLibraryHint') }}</p>
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
              <span>{{ t('screening.config.ruleInputHint', { count: ligandCount }) }}</span>
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
