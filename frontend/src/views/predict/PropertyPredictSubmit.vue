<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import { uploadFile } from '@/api/files'
import { exportCandidateSet, listCandidateSets } from '@/api/compounds'
import { submitToolTask } from '@/api/predict'
import { listProjects } from '@/api/projects'
import { getTarget, listStructures, listTargets } from '@/api/targets'
import ModelSelect from '@/components/design/ModelSelect.vue'
import ModelParameterForm from '@/components/design/ModelParameterForm.vue'
import Smiles2DCell from '@/components/tasks/Smiles2DCell.vue'
import { useModelOptions } from '@/composables/useModelOptions'
import {
  buildDefaultValues,
  normalizeParameters,
  validateParameters,
  type ParameterValues
} from '@/domain/tools/parameterSchema'
import {
  ADMET_TOOL_SLUG,
  PREDICT_DEFAULT_TASK_GROUPS,
  PREDICT_GROUP_I18N,
  PREDICT_TASK_GROUPS
} from '@/types/predict'
import type { PredictTaskGroup } from '@/types/predict'
import type { CandidateSet } from '@/types/compounds'
import type { ResearchProject } from '@/types/projects'
import type { ProteinDetail, ProteinStructureDetail, TargetSummary } from '@/types/targets'

const props = withDefaults(
  defineProps<{
    projectIdOverride?: string
    /** 宿主直接指定初始预测类型（向导把亲和力单独做成一步时用）。 */
    initialType?: 'admet' | 'affinity'
    initialGroups?: PredictTaskGroup[]
  }>(),
  { projectIdOverride: '', initialType: undefined, initialGroups: undefined }
)

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

/**
 * 项目上下文解析顺序：宿主传入 > URL query > 路由参数。
 * 三者都没有时页面**不能**再当作可用状态——任务的输入物化（standard_input_uploads →
 * ArtifactVersion）依赖 project_id，缺项目连"直接上传文件"都会在执行器阶段失败，
 * 所以这里保留空值并引导用户用页面上的项目选择器补选。
 */
const projectId = computed(() => {
  if (props.projectIdOverride) return props.projectIdOverride
  const raw = route.query.project_id
  if (typeof raw === 'string' && raw) return raw
  const paramId = route.params?.projectId
  return typeof paramId === 'string' ? paramId : ''
})

const projects = ref<ResearchProject[]>([])
const projectOptions = computed(() => projects.value.map(item => ({ label: item.name, value: item.id })))
const projectName = computed(
  () => projects.value.find(item => item.id === projectId.value)?.name ?? ''
)

const source = ref<'upload' | 'candidate' | 'smiles'>('upload')
const smilesFile = ref<File | null>(null)
const smilesFileName = ref('')
/** 上游（分子生成 / 虚拟筛选等）已经把文件落盘时，直接用 file_id 当输入，不再重复上传。 */
const preuploadedFileId = ref('')
const preuploadedFilename = ref('')
/** 手动粘贴 SMILES：DrugFlow 式「即时预览后再提交」。 */
const inlineSmiles = ref('')
const filePreview = ref<string[]>([])
const candidateSets = ref<CandidateSet[]>([])
const candidateSetId = ref<string>('')
const admetParams = ref<ParameterValues>({})

/** 预览面板最多铺 12 个骨架，避免几十个分子把页面撑爆。 */
const PREVIEW_LIMIT = 12

const EXAMPLE_SMILES = [
  'CC(=O)Oc1ccccc1C(=O)O', // Aspirin
  'CC(C)Cc1ccc(cc1)C(C)C(=O)O', // Ibuprofen
  'Cn1cnc2c1c(=O)n(C)c(=O)n2C', // Caffeine
  'CN(C)C(=N)NC(=N)N', // Metformin
  'CC(=O)Nc1ccc(O)cc1', // Acetaminophen
  'CC(C)c1c(C(=O)Nc2ccccc2)c(-c2ccccc2)c(-c2ccc(F)cc2)n1CCC(O)CC(O)CC(=O)O' // Atorvastatin
]

// 同类 ADMET/性质预测模型可自由选择；默认 molp-pc。
const {
  options: modelOptions,
  selectedSlug,
  selectedOption: admetSelected,
  loading: modelLoading,
  load: loadModels
} = useModelOptions('admet_prediction', { defaultSlug: ADMET_TOOL_SLUG })

// 预测类型：ADMET 分子性质 / 结合亲和力（亲和力属于评估验证→性质预测环节）。
// 宿主可以固定初始类型，避免"点了亲和力这一步却停在上传 SMILES 的表单上"。
const predictType = ref<'admet' | 'affinity'>(
  props.initialType === 'affinity' || route.query.type === 'affinity' ? 'affinity' : 'admet'
)
const {
  options: affinityOptions,
  selectedSlug: affinitySlug,
  selectedOption: affinitySelected,
  loading: affinityLoading,
  load: loadAffinityModels
} = useModelOptions('affinity', { defaultSlug: 'msign-affinity-prediction' })

const proteinPdbFile = ref<File | null>(null)
const proteinPdbName = ref('')
const ligandSdfFile = ref<File | null>(null)
const ligandSdfName = ref('')
const ligandSmilesFile = ref<File | null>(null)
const ligandSmilesName = ref('')
const affinityParams = ref<ParameterValues>({})

// 亲和力的输入来源：本地上传 / 项目内已有资产（靶点结构 + 候选集）。
const affinitySource = ref<'upload' | 'project'>('upload')
const targets = ref<TargetSummary[]>([])
const proteins = ref<ProteinDetail[]>([])
const structures = ref<ProteinStructureDetail[]>([])
const selectedTargetId = ref('')
const selectedProteinId = ref('')
const selectedStructureId = ref('')
const affinityCandidateSetId = ref('')

const admetSchema = computed(() => admetSelected.value?.parameterSchema ?? null)
const affinitySchema = computed(() => affinitySelected.value?.parameterSchema ?? null)
const affinityInputFields = computed(() => affinitySelected.value?.inputFields ?? [])

const targetOptions = computed(() =>
  targets.value.map(item => ({ label: item.name, value: item.id }))
)
const proteinOptions = computed(() => proteins.value.map(item => ({ label: item.name, value: item.id })))
/** 只有落过盘的结构才能当输入（`file:<id>` 可物化成 ArtifactVersion）。 */
const structureOptions = computed(() =>
  structures.value
    .filter(item => Boolean(item.prepared_file_id || item.structure_file_id))
    .map(item => ({
      label: buildStructureLabel(item),
      value: item.id
    }))
)
const selectedStructure = computed(
  () => structures.value.find(item => item.id === selectedStructureId.value) ?? null
)
const selectedStructureFileId = computed(
  () => selectedStructure.value?.prepared_file_id || selectedStructure.value?.structure_file_id || ''
)

/** 该模型是否需要配体输入（SDF 或 SMILES 表任一）。 */
const ligandFieldsNeeded = computed(() => {
  const fields = affinityInputFields.value
  return fields.includes('ligand_sdf') || fields.includes('ligand_smiles')
})

const affinityCanSubmit = computed(() => {
  if (submitting.value || !projectId.value) return false
  const fields = affinityInputFields.value
  if (affinitySource.value === 'project') {
    if (fields.includes('protein_pdb') && !selectedStructureFileId.value) return false
    if (!fields.includes('protein_pdb') && fields.length === 0) return false
    if (ligandFieldsNeeded.value && !affinityCandidateSetId.value) return false
    return validateParameters(affinitySchema.value, affinityParams.value).length === 0
  }
  if (fields.includes('protein_pdb') && !proteinPdbFile.value) return false
  if (ligandFieldsNeeded.value) {
    const hasLigand =
      (fields.includes('ligand_sdf') && Boolean(ligandSdfFile.value)) ||
      (fields.includes('ligand_smiles') && Boolean(ligandSmilesFile.value))
    if (!hasLigand) return false
  }
  return validateParameters(affinitySchema.value, affinityParams.value).length === 0
})

watch(
  admetSchema,
  schema => {
    admetParams.value = buildDefaultValues(schema)
  },
  { immediate: true }
)

watch(
  affinitySchema,
  schema => {
    affinityParams.value = buildDefaultValues(schema)
  },
  { immediate: true }
)

watch(
  projectId,
  id => {
    candidateSetId.value = ''
    affinityCandidateSetId.value = ''
    selectedTargetId.value = ''
    candidateSets.value = []
    targets.value = []
    if (id) {
      void loadCandidateSets()
      void loadTargets()
    }
  },
  { immediate: true }
)

watch(selectedTargetId, id => {
  selectedProteinId.value = ''
  selectedStructureId.value = ''
  proteins.value = []
  structures.value = []
  if (id) {
    void loadProteins(id)
  }
})

watch(selectedProteinId, id => {
  selectedStructureId.value = ''
  structures.value = []
  if (id) {
    void loadStructures(id)
  }
})

const selectedGroups = ref<PredictTaskGroup[]>(
  props.initialGroups?.length ? [...props.initialGroups] : [...PREDICT_DEFAULT_TASK_GROUPS]
)
const submitting = ref(false)
const formError = ref('')

const groupOptions = computed(() =>
  PREDICT_TASK_GROUPS.map(group => ({
    label: t(`predict.submit.${PREDICT_GROUP_I18N[group]}`),
    value: group
  }))
)

const candidateSetOptions = computed(() =>
  candidateSets.value.map(item => ({ label: item.name, value: item.id }))
)

/**
 * 从纯文本里抽取 SMILES：兼容
 * - 每行一个 SMILES；
 * - 逗号 / Tab 分隔的 CSV，自动识别 `smiles` 列表头（无表头时取第一列）；
 * - 忽略空行与表头行。
 */
function isLikelySmiles(value: string): boolean {
  const text = value.trim()
  if (!text || /\s/.test(text)) return false
  if (!/^[A-Za-z0-9@+\-[\]()\\/=#$.%:;>*^~]+$/.test(text)) return false
  // 至少要有一个 SMILES 里常见的原子记号，避免把 "id" / "name" 之类的表头值当分子
  return /[BCNOPSFIcnops]/.test(text)
}

function extractSmiles(raw: string): string[] {
  const lines = raw.replace(/^﻿/, '').split(/\r?\n/)
  const result: string[] = []
  let smilesIndex = -1
  let headerChecked = false
  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) continue
    const delimiter = line.includes('\t') ? '\t' : line.includes(',') ? ',' : ''
    const cells = delimiter
      ? line.split(delimiter).map(cell => cell.trim().replace(/^"(.*)"$/, '$1'))
      : [line]
    if (!headerChecked) {
      headerChecked = true
      const index = cells.findIndex(cell => /^(canonical_)?smiles$/i.test(cell))
      if (index >= 0) {
        smilesIndex = index
        continue
      }
    }
    const value = (smilesIndex >= 0 ? cells[smilesIndex] : cells[0]) ?? ''
    if (isLikelySmiles(value)) {
      result.push(value.trim())
    }
  }
  return result
}

const previewMolecules = computed(() => {
  if (source.value === 'smiles') {
    return extractSmiles(inlineSmiles.value)
  }
  if (source.value === 'upload') {
    return filePreview.value
  }
  return []
})
const previewSlice = computed(() => previewMolecules.value.slice(0, PREVIEW_LIMIT))
const showLivePreview = computed(() => {
  if (predictType.value !== 'admet') return false
  if (source.value === 'smiles') return true
  // 上游交接的 file_id 没有本地内容可读，避免显示「0 个有效分子」的空预览
  return source.value === 'upload' && !preuploadedFileId.value
})

watch(smilesFile, async file => {
  filePreview.value = []
  if (!file) return
  try {
    filePreview.value = extractSmiles(await file.text())
  } catch {
    filePreview.value = []
  }
})

/** 加载示例：一键填入 6 个经典药物分子，方便先看到预览效果。 */
function loadExampleSmiles(): void {
  inlineSmiles.value = EXAMPLE_SMILES.join('\n')
  message.success(t('predict.submit.exampleLoaded'))
}

function copySmiles(value: string): void {
  const clipboard = typeof navigator !== 'undefined' ? navigator.clipboard : undefined
  if (clipboard && typeof clipboard.writeText === 'function') {
    void clipboard.writeText(value).then(
      () => message.success(t('predict.submit.copied')),
      () => undefined
    )
  }
}

function removeInlineSmilesAt(index: number): void {
  const values = extractSmiles(inlineSmiles.value)
  values.splice(index, 1)
  inlineSmiles.value = values.join('\n')
}

function buildInlineSmilesFile(): File {
  const csv = ['smiles', ...extractSmiles(inlineSmiles.value)].join('\n')
  return new File([csv], `inline_smiles_${Date.now()}.csv`, { type: 'text/csv' })
}

/**
 * 上游跳转带过来的上下文：
 * - `candidate_set_id`：直接切到候选集模式并选中；
 * - `file_id`（+ 可选 `filename`）：文件已落盘，上传模式展示为已选文件，提交时直接复用。
 */
let appliedHandoffKey = ''
function applyQueryHandoff(): void {
  const candidateQuery = route.query.candidate_set_id
  const fileQuery = route.query.file_id
  const filenameQuery = route.query.filename
  const key = `${String(candidateQuery ?? '')}|${String(fileQuery ?? '')}|${String(
    filenameQuery ?? ''
  )}|${projectId.value}`
  if (key === appliedHandoffKey) return
  appliedHandoffKey = key

  if (typeof candidateQuery === 'string' && candidateQuery) {
    source.value = 'candidate'
    candidateSetId.value = candidateQuery
    smilesFile.value = null
    smilesFileName.value = ''
    preuploadedFileId.value = ''
    preuploadedFilename.value = ''
    return
  }
  if (typeof fileQuery === 'string' && fileQuery) {
    source.value = 'upload'
    preuploadedFileId.value = fileQuery
    preuploadedFilename.value = typeof filenameQuery === 'string' ? filenameQuery : ''
    smilesFile.value = null
    smilesFileName.value = ''
    candidateSetId.value = ''
    filePreview.value = []
  }
}

watch(
  () => route.query,
  () => applyQueryHandoff()
)

const canSubmit = computed(() => {
  if (predictType.value === 'affinity') {
    return affinityCanSubmit.value
  }
  if (submitting.value || !projectId.value || !selectedGroups.value.length) {
    return false
  }
  if (validateParameters(admetSchema.value, admetParams.value).length > 0) {
    return false
  }
  if (source.value === 'upload') {
    return Boolean(smilesFile.value || preuploadedFileId.value)
  }
  if (source.value === 'smiles') {
    return previewMolecules.value.length > 0
  }
  return Boolean(candidateSetId.value)
})

function buildStructureLabel(structure: ProteinStructureDetail): string {
  const parts: string[] = []
  if (structure.source_type) parts.push(structure.source_type)
  if (structure.prepared_file_id) parts.push(t('predict.submit.structurePrepared'))
  if (typeof structure.plddt_mean === 'number') {
    parts.push(`pLDDT ${structure.plddt_mean.toFixed(2)}`)
  }
  parts.push(structure.id.slice(0, 8))
  return parts.join(' · ')
}

/** 选择项目后写回 URL，刷新/分享都能回到同一上下文。 */
function handleProjectChange(value: unknown): void {
  const id = typeof value === 'string' ? value : ''
  const query = { ...route.query }
  if (id) {
    query.project_id = id
  } else {
    delete query.project_id
  }
  void router.replace({ query })
}

function handleBeforeUpload(file: File): boolean {
  smilesFile.value = file
  smilesFileName.value = file.name
  // 本地重新选了文件，就不再复用上游落盘的 file_id
  preuploadedFileId.value = ''
  preuploadedFilename.value = ''
  return false
}

function handleProteinUpload(file: File): boolean {
  proteinPdbFile.value = file
  proteinPdbName.value = file.name
  return false
}

function handleLigandSdfUpload(file: File): boolean {
  ligandSdfFile.value = file
  ligandSdfName.value = file.name
  return false
}

function handleLigandSmilesUpload(file: File): boolean {
  ligandSmilesFile.value = file
  ligandSmilesName.value = file.name
  return false
}

async function handleAffinitySubmit(): Promise<void> {
  formError.value = ''
  if (!affinityCanSubmit.value) {
    return
  }
  submitting.value = true
  try {
    const fields = new Set(affinityInputFields.value)
    const standardInputUploads: Record<string, string> = {}
    if (affinitySource.value === 'project') {
      if (fields.has('protein_pdb')) {
        if (!selectedStructureFileId.value) {
          throw new Error(t('predict.submit.needStructure'))
        }
        standardInputUploads.protein_pdb = selectedStructureFileId.value
      }
      if (fields.has('ligand_smiles')) {
        if (!affinityCandidateSetId.value) {
          throw new Error(t('predict.submit.needCandidateSet'))
        }
        const exported = await exportCandidateSet(affinityCandidateSetId.value)
        if (!exported.data.file_id) {
          throw new Error(t('predict.submit.uploadFailed'))
        }
        standardInputUploads.ligand_smiles = exported.data.file_id
      }
    } else {
      if (fields.has('protein_pdb') && proteinPdbFile.value) {
        standardInputUploads.protein_pdb = (await uploadFile(proteinPdbFile.value)).data.id
      }
      if (fields.has('ligand_sdf') && ligandSdfFile.value) {
        standardInputUploads.ligand_sdf = (await uploadFile(ligandSdfFile.value)).data.id
      }
      if (fields.has('ligand_smiles') && ligandSmilesFile.value) {
        standardInputUploads.ligand_smiles = (await uploadFile(ligandSmilesFile.value)).data.id
      }
    }
    const task = await submitToolTask({
      toolSlug: affinitySlug.value,
      projectId: projectId.value || undefined,
      name: `亲和力预测 ${new Date().toISOString().slice(0, 10)}`,
      params: normalizeParameters(affinitySchema.value, affinityParams.value),
      standardInputUploads
    })
    message.success(t('predict.submit.success'))
    await router.push(`/tasks/${task.id}`)
  } catch (error) {
    formError.value = error instanceof Error ? error.message : t('predict.submit.submitFailed')
  } finally {
    submitting.value = false
  }
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
    return
  }
  try {
    const response = await listTargets(projectId.value, { page: 1, page_size: 100 })
    targets.value = response.data.items
  } catch {
    targets.value = []
  }
}

async function loadProteins(targetId: string): Promise<void> {
  try {
    const response = await getTarget(targetId)
    proteins.value = response.data.proteins ?? []
  } catch {
    proteins.value = []
  }
}

async function loadStructures(proteinId: string): Promise<void> {
  try {
    const response = await listStructures(proteinId)
    structures.value = response.data.items
  } catch {
    structures.value = []
  }
}

async function loadCandidateSets(): Promise<void> {
  if (!projectId.value) {
    return
  }
  try {
    const response = await listCandidateSets(projectId.value, { page: 1, page_size: 100 })
    candidateSets.value = response.data.items
  } catch {
    candidateSets.value = []
  }
}

async function resolveMoleculesFileId(): Promise<string> {
  if (source.value === 'upload') {
    if (preuploadedFileId.value) {
      return preuploadedFileId.value
    }
    if (!smilesFile.value) {
      throw new Error(t('predict.submit.needFile'))
    }
    const uploaded = await uploadFile(smilesFile.value)
    return uploaded.data.id
  }
  if (source.value === 'smiles') {
    if (!extractSmiles(inlineSmiles.value).length) {
      throw new Error(t('predict.submit.needSmiles'))
    }
    const uploaded = await uploadFile(buildInlineSmilesFile())
    return uploaded.data.id
  }
  if (!candidateSetId.value) {
    throw new Error(t('predict.submit.needFile'))
  }
  const exported = await exportCandidateSet(candidateSetId.value)
  const fileId = exported.data.file_id
  if (!fileId) {
    throw new Error(t('predict.submit.uploadFailed'))
  }
  return fileId
}

async function handleSubmit(): Promise<void> {
  if (predictType.value === 'affinity') {
    await handleAffinitySubmit()
    return
  }
  formError.value = ''
  if (!projectId.value) {
    formError.value = t('predict.submit.needProjectSubmit')
    return
  }
  if (source.value === 'upload' && !smilesFile.value && !preuploadedFileId.value) {
    formError.value = t('predict.submit.needFile')
    return
  }
  if (source.value === 'smiles' && !previewMolecules.value.length) {
    formError.value = t('predict.submit.needSmiles')
    return
  }
  if (source.value === 'candidate' && !candidateSetId.value) {
    formError.value = t('predict.submit.needFile')
    return
  }
  if (!selectedGroups.value.length) {
    formError.value = t('predict.submit.needGroups')
    return
  }

  submitting.value = true
  try {
    const fileId = await resolveMoleculesFileId()
    const task = await submitToolTask({
      toolSlug: selectedSlug.value,
      projectId: projectId.value || undefined,
      name: `ADMET 性质预测 ${new Date().toISOString().slice(0, 10)}`,
      params: normalizeParameters(admetSchema.value, admetParams.value),
      standardInputUploads: { smiles_csv: fileId }
    })
    message.success(t('predict.submit.success'))
    await router.push(`/tasks/${task.id}/predictions`)
  } catch (error) {
    formError.value = error instanceof Error ? error.message : t('predict.submit.submitFailed')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  applyQueryHandoff()
  void loadProjects()
  void loadModels()
  void loadAffinityModels()
  void loadCandidateSets()
})
</script>

<template>
  <main class="predict-submit" data-testid="predict-submit-page">
    <!-- 被设计流程内嵌时（传了 projectIdOverride）不渲染页面头：
         外层已有步骤标题，这里的「性质预测 / 勾选指标组后提交 ADMET 任务」反而与
         当前正在做的亲和力预测对不上。 -->
    <AppPageHeader
      v-if="!projectIdOverride"
      :title="t('predict.submit.title')"
      :subtitle="t('predict.submit.subtitle')"
    />

    <a-card
      v-if="!projectIdOverride"
      class="predict-submit__card"
      :title="t('predict.submit.project')"
    >
      <a-select
        :value="projectId || undefined"
        style="width: 320px"
        show-search
        option-filter-prop="label"
        :options="projectOptions"
        :placeholder="t('predict.submit.projectPlaceholder')"
        data-testid="predict-submit-project"
        @change="handleProjectChange"
      />
      <p v-if="!projectId" class="predict-submit__hint">{{ t('predict.submit.projectHint') }}</p>
      <p v-else-if="projectName" class="predict-submit__selected">
        {{ t('predict.submit.projectCurrent') }}: {{ projectName }}
      </p>
    </a-card>

    <a-card class="predict-submit__card" :title="t('predict.submit.type')">
      <a-radio-group v-model:value="predictType" button-style="solid">
        <a-radio-button value="admet" data-testid="predict-type-admet">
          {{ t('predict.submit.typeAdmet') }}
        </a-radio-button>
        <a-radio-button value="affinity" data-testid="predict-type-affinity">
          {{ t('predict.submit.typeAffinity') }}
        </a-radio-button>
      </a-radio-group>
    </a-card>

    <a-card v-if="predictType === 'admet'" class="predict-submit__card" :title="t('design.modelSelect.label')">
      <ModelSelect v-model="selectedSlug" :options="modelOptions" :loading="modelLoading" />
      <ModelParameterForm
        v-if="admetSchema"
        v-model="admetParams"
        :schema="admetSchema"
        :disabled="submitting"
      />
    </a-card>
    <a-card v-else class="predict-submit__card" :title="t('design.modelSelect.label')">
      <ModelSelect v-model="affinitySlug" :options="affinityOptions" :loading="affinityLoading" />
      <ModelParameterForm
        v-if="affinitySchema"
        v-model="affinityParams"
        :schema="affinitySchema"
        :disabled="submitting"
      />
    </a-card>

    <a-card v-if="predictType === 'admet'" class="predict-submit__card" :title="t('predict.submit.source')">
      <a-radio-group v-model:value="source" button-style="solid">
        <a-radio-button value="upload" data-testid="predict-submit-source-upload">
          {{ t('predict.submit.sourceUpload') }}
        </a-radio-button>
        <a-radio-button value="candidate" data-testid="predict-submit-source-candidate">
          {{ t('predict.submit.sourceCandidateSet') }}
        </a-radio-button>
        <a-radio-button value="smiles" data-testid="predict-submit-source-smiles">
          {{ t('predict.submit.sourceSmiles') }}
        </a-radio-button>
      </a-radio-group>

      <div v-if="source === 'upload'" class="predict-submit__block">
        <a-upload
          :before-upload="handleBeforeUpload"
          :max-count="1"
          accept=".csv"
          :file-list="[]"
        >
          <a-button>{{ t('predict.submit.chooseFile') }}</a-button>
        </a-upload>
        <p class="predict-submit__hint">{{ t('predict.submit.uploadHint') }}</p>
        <p v-if="smilesFileName" class="predict-submit__selected">
          {{ t('predict.submit.selectedFile') }}: {{ smilesFileName }}
        </p>
        <template v-if="preuploadedFileId">
          <p class="predict-submit__selected" data-testid="predict-submit-preuploaded">
            {{ t('predict.submit.preuploadedFile') }}:
            {{ preuploadedFilename || preuploadedFileId }}
          </p>
          <p class="predict-submit__hint">{{ t('predict.submit.preuploadedHint') }}</p>
        </template>
      </div>

      <div v-else-if="source === 'candidate'" class="predict-submit__block">
        <a-select
          v-model:value="candidateSetId"
          style="width: 320px"
          :options="candidateSetOptions"
          :placeholder="t('predict.submit.candidateSetPlaceholder')"
          :not-found-content="t('predict.submit.noCandidateSets')"
        />
        <p v-if="!projectId" class="predict-submit__hint">{{ t('predict.submit.needProject') }}</p>
      </div>

      <div v-else class="predict-submit__block">
        <a-textarea
          v-model:value="inlineSmiles"
          class="predict-submit__smiles-input"
          :rows="6"
          :placeholder="t('predict.submit.smilesPlaceholder')"
          data-testid="predict-submit-smiles-input"
        />
        <div class="predict-submit__actions">
          <a-button data-testid="predict-submit-load-example" @click="loadExampleSmiles">
            {{ t('predict.submit.loadExample') }}
          </a-button>
          <a-button v-if="inlineSmiles" @click="inlineSmiles = ''">
            {{ t('predict.submit.clearSmiles') }}
          </a-button>
        </div>
        <p class="predict-submit__hint">{{ t('predict.submit.smilesHint') }}</p>
      </div>

      <div v-if="showLivePreview" class="predict-submit__preview" data-testid="predict-submit-preview">
        <div class="predict-submit__preview-head">
          <strong>{{ t('predict.submit.previewTitle') }}</strong>
          <span data-testid="predict-submit-preview-count">
            {{ t('predict.submit.previewCount', { count: previewMolecules.length }) }}
          </span>
        </div>
        <p v-if="!previewMolecules.length" class="predict-submit__hint">
          {{ t('predict.submit.previewEmpty') }}
        </p>
        <div v-else class="predict-submit__preview-grid">
          <div
            v-for="(smiles, index) in previewSlice"
            :key="`${smiles}-${index}`"
            class="predict-submit__preview-item"
            data-testid="predict-submit-preview-item"
          >
            <Smiles2DCell :smiles="smiles" :width="120" :height="76" />
            <code class="predict-submit__smiles-text" :title="smiles">{{ smiles }}</code>
            <div class="predict-submit__preview-actions">
              <a-button type="link" size="small" @click="copySmiles(smiles)">
                {{ t('predict.submit.copySmiles') }}
              </a-button>
              <a-button
                v-if="source === 'smiles'"
                type="link"
                size="small"
                data-testid="predict-submit-preview-remove"
                @click="removeInlineSmilesAt(index)"
              >
                {{ t('predict.submit.removeSmiles') }}
              </a-button>
            </div>
          </div>
        </div>
        <p v-if="previewMolecules.length > PREVIEW_LIMIT" class="predict-submit__hint">
          {{ t('predict.submit.previewMore', { shown: PREVIEW_LIMIT }) }}
        </p>
      </div>
    </a-card>

    <a-card v-if="predictType === 'admet'" class="predict-submit__card" :title="t('predict.submit.groups')">
      <p class="predict-submit__hint">{{ t('predict.submit.groupsHint') }}</p>
      <a-checkbox-group
        v-model:value="selectedGroups"
        :options="groupOptions"
        data-testid="predict-submit-groups"
      />
    </a-card>

    <a-card v-if="predictType === 'affinity'" class="predict-submit__card" :title="t('predict.submit.affinityInputs')">
      <a-radio-group v-model:value="affinitySource" button-style="solid">
        <a-radio-button value="upload" data-testid="predict-affinity-source-upload">
          {{ t('predict.submit.affinitySourceUpload') }}
        </a-radio-button>
        <a-radio-button value="project" data-testid="predict-affinity-source-project">
          {{ t('predict.submit.affinitySourceProject') }}
        </a-radio-button>
      </a-radio-group>

      <template v-if="affinitySource === 'upload'">
        <div v-if="affinityInputFields.includes('protein_pdb')" class="predict-submit__block">
          <p class="predict-submit__hint">{{ t('predict.submit.proteinPdb') }}</p>
          <a-upload :before-upload="handleProteinUpload" :max-count="1" accept=".pdb,.cif,.ent" :file-list="[]">
            <a-button>{{ t('predict.submit.chooseInputFile') }}</a-button>
          </a-upload>
          <p v-if="proteinPdbName" class="predict-submit__selected">{{ proteinPdbName }}</p>
        </div>
        <div v-if="affinityInputFields.includes('ligand_sdf')" class="predict-submit__block">
          <p class="predict-submit__hint">{{ t('predict.submit.ligandSdf') }}</p>
          <a-upload :before-upload="handleLigandSdfUpload" :max-count="1" accept=".sdf" :file-list="[]">
            <a-button>{{ t('predict.submit.chooseInputFile') }}</a-button>
          </a-upload>
          <p v-if="ligandSdfName" class="predict-submit__selected">{{ ligandSdfName }}</p>
        </div>
        <div v-if="affinityInputFields.includes('ligand_smiles')" class="predict-submit__block">
          <p class="predict-submit__hint">{{ t('predict.submit.ligandSmiles') }}</p>
          <a-upload :before-upload="handleLigandSmilesUpload" :max-count="1" accept=".csv" :file-list="[]">
            <a-button>{{ t('predict.submit.chooseInputFile') }}</a-button>
          </a-upload>
          <p v-if="ligandSmilesName" class="predict-submit__selected">{{ ligandSmilesName }}</p>
        </div>
      </template>

      <template v-else>
        <p v-if="!projectId" class="predict-submit__hint">{{ t('predict.submit.needProject') }}</p>
        <template v-if="affinityInputFields.includes('protein_pdb')">
          <div class="predict-submit__block">
            <p class="predict-submit__hint">{{ t('predict.submit.target') }}</p>
            <a-select
              v-model:value="selectedTargetId"
              style="width: 320px"
              :options="targetOptions"
              :placeholder="t('predict.submit.targetPlaceholder')"
              :not-found-content="t('predict.submit.noTargets')"
              data-testid="predict-affinity-target"
            />
          </div>
          <div v-if="selectedTargetId" class="predict-submit__block">
            <p class="predict-submit__hint">{{ t('predict.submit.protein') }}</p>
            <a-select
              v-model:value="selectedProteinId"
              style="width: 320px"
              :options="proteinOptions"
              :placeholder="t('predict.submit.proteinPlaceholder')"
              :not-found-content="t('predict.submit.noProteins')"
              data-testid="predict-affinity-protein"
            />
          </div>
          <div v-if="selectedProteinId" class="predict-submit__block">
            <p class="predict-submit__hint">{{ t('predict.submit.structure') }}</p>
            <a-select
              v-model:value="selectedStructureId"
              style="width: 420px"
              :options="structureOptions"
              :placeholder="t('predict.submit.structurePlaceholder')"
              :not-found-content="t('predict.submit.noStructures')"
              data-testid="predict-affinity-structure"
            />
            <p v-if="selectedStructureFileId" class="predict-submit__selected">
              {{ t('predict.submit.structureSelected') }}: {{ selectedStructureFileId }}
            </p>
          </div>
        </template>
        <div v-if="ligandFieldsNeeded && affinityInputFields.includes('ligand_smiles')" class="predict-submit__block">
          <p class="predict-submit__hint">{{ t('predict.submit.candidateSet') }}</p>
          <a-select
            v-model:value="affinityCandidateSetId"
            style="width: 320px"
            :options="candidateSetOptions"
            :placeholder="t('predict.submit.candidateSetPlaceholder')"
            :not-found-content="t('predict.submit.noCandidateSets')"
            data-testid="predict-affinity-candidateset"
          />
          <p class="predict-submit__hint">{{ t('predict.submit.candidateSetExportHint') }}</p>
        </div>
      </template>

      <p class="predict-submit__hint">{{ t('predict.submit.affinityHint') }}</p>
    </a-card>

    <div class="predict-submit__footer">
      <a-alert v-if="formError" type="error" show-icon :message="formError" data-testid="predict-submit-error" />
      <a-button
        type="primary"
        size="large"
        :loading="submitting"
        :disabled="!canSubmit"
        data-testid="predict-submit-button"
        @click="handleSubmit"
      >
        {{ submitting ? t('predict.submit.submitting') : t('predict.submit.submit') }}
      </a-button>
    </div>
  </main>
</template>

<style scoped lang="less">
.predict-submit {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
}

.predict-submit__notice {
  margin-bottom: 0;
}

.predict-submit__block {
  margin-top: 16px;
}

.predict-submit__hint {
  margin: 8px 0 0;
  color: var(--ant-color-text-secondary, var(--theme-text-secondary));
}

.predict-submit__selected {
  margin: 8px 0 0;
  font-weight: 600;
}

.predict-submit__smiles-input {
  font-family: var(--ant-font-family-code, monospace);
}

.predict-submit__actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.predict-submit__preview {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed var(--ant-color-border, var(--theme-border));
}

.predict-submit__preview-head {
  display: flex;
  gap: 12px;
  align-items: baseline;
  margin-bottom: 8px;
}

.predict-submit__preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: 12px;
}

.predict-submit__preview-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
  padding: 8px;
  border: 1px solid var(--ant-color-border, var(--theme-border));
  border-radius: 8px;
}

.predict-submit__smiles-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  width: 100%;
  min-height: 34px;
  overflow: hidden;
  text-overflow: ellipsis;
  word-break: break-all;
  font-size: 12px;
  line-height: 1.4;
  text-align: center;
}

.predict-submit__preview-actions {
  display: flex;
  gap: 4px;
}

.predict-submit__footer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: flex-start;
}
</style>
