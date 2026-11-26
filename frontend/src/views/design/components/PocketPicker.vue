<template>
  <div class="pocket-picker" data-testid="pocket-picker">
    <a-steps :current="currentStep" size="small" class="pocket-stepper" data-testid="pocket-stepper">
      <a-step v-if="!hideProjectSelect" :title="t('design.pocket.project')" />
      <a-step :title="t('design.pocket.target')" />
      <a-step :title="t('design.pocket.protein')" />
      <a-step :title="t('design.pocket.structure')" />
      <a-step v-if="!hidePocketSelect" :title="t('design.pocket.pocket')" />
    </a-steps>

    <a-spin :spinning="loadingProjects">
      <a-row :gutter="16">
        <a-col v-if="!hideProjectSelect" :xs="24" :sm="12" :lg="8">
          <a-form-item :label="t('design.pocket.project')">
            <a-select
              v-model:value="selectedProject"
              show-search
              option-filter-prop="label"
              :placeholder="t('design.pocket.projectPlaceholder')"
              data-testid="pocket-project"
              @change="handleProjectChange"
            >
              <a-select-option
                v-for="project in projects"
                :key="project.id"
                :value="project.id"
                :label="project.name"
              >
                {{ project.name }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>

        <a-col :xs="24" :sm="12" :lg="8">
          <a-form-item :label="t('design.pocket.target')">
            <a-select
              v-model:value="selectedTarget"
              :disabled="!selectedProject"
              :placeholder="t('design.pocket.selectPlaceholder')"
              :loading="loadingTargets"
              data-testid="pocket-target"
              @change="handleTargetChange"
            >
              <a-select-option v-for="target in targets" :key="target.id" :value="target.id">
                {{ target.name }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>

        <a-col :xs="24" :sm="12" :lg="8">
          <a-form-item :label="t('design.pocket.protein')">
            <a-select
              v-model:value="selectedProtein"
              :disabled="!selectedTarget"
              :placeholder="t('design.pocket.selectPlaceholder')"
              :loading="loadingProteins"
              data-testid="pocket-protein"
              @change="handleProteinChange"
            >
              <a-select-option v-for="protein in proteins" :key="protein.id" :value="protein.id">
                {{ protein.name }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>

        <a-col :xs="24" :sm="12" :lg="8">
          <a-form-item :label="t('design.pocket.structure')">
            <a-select
              v-model:value="selectedStructure"
              :disabled="!selectedProtein"
              :placeholder="t('design.pocket.selectPlaceholder')"
              :loading="loadingStructures"
              data-testid="pocket-structure"
              @change="handleStructureChange"
            >
              <a-select-option
                v-for="(structure, index) in structures"
                :key="structure.id"
                :value="structure.id"
              >
                {{ structureLabel(structure, index) }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>

        <a-col v-if="!hidePocketSelect" :xs="24" :sm="12" :lg="8">
          <a-form-item :label="t('design.pocket.pocket')">
            <a-select
              v-model:value="selectedPocket"
              :disabled="!selectedStructure"
              :placeholder="t('design.pocket.selectPlaceholder')"
              :loading="loadingPockets"
              data-testid="pocket-pocket"
              @change="handlePocketChange"
            >
              <a-select-option v-for="pocket in pockets" :key="pocket.id" :value="pocket.id">
                {{ pocketLabel(pocket) }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
      </a-row>

      <!-- 上游缺结构：就地预测结构 -->
      <section v-if="selectedProtein && !structures.length" class="relay-panel" data-testid="pocket-missing-structure">
        <div class="relay-title">{{ t('design.upstream.missingStructure') }}</div>
        <StructurePredictForm
          :protein-id="selectedProtein"
          @submitted="snapshotStructures"
          @completed="handleStructurePredicted"
          @error="onRelayError"
        />
      </section>

      <!-- 上游缺已选口袋：就地预测 / 选定 -->
      <section v-else-if="!hidePocketSelect && selectedStructure && !pockets.length" class="relay-panel" data-testid="pocket-missing-pocket">
        <div class="relay-title">{{ t('design.upstream.missingPocket') }}</div>
        <PocketPredictPanel
          :structure-id="selectedStructure"
          @selected="handleRelayPocketSelected"
          @predicted="onRelayPredicted"
        />
      </section>

      <section v-if="showPreview && modelValue" class="pocket-preview" data-testid="pocket-preview">
        <div class="pocket-preview__title">{{ t('design.molecule.pocketPreview') }}</div>
        <div v-if="previewScene" class="pocket-preview__viewer">
          <PocketPreviewViewer
            :scene="previewScene"
            variant="compact"
            mode="pocket"
            :voxel-grid="previewVoxelGrid"
            :allow-native-fullscreen="false"
          />
        </div>
        <div v-else class="pocket-preview__empty" data-testid="pocket-preview-empty">
          {{ previewFallbackMessage }}
        </div>
      </section>

      <a-alert v-if="error" type="warning" show-icon :message="error" />
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRequestSequence } from '@/composables/useRequestSequence'
import {
  listDesignProjects,
  listProjectTargets,
  listProteinStructures,
  listStructurePockets,
  loadTargetProteins,
} from '@/api/design'
import { getFileInfo } from '@/api/files'
import StructurePredictForm from '@/components/design/StructurePredictForm.vue'
import PocketPredictPanel from '@/components/design/PocketPredictPanel.vue'
import { selectNewlyAdded } from '@/domain/design/pipeline'
import { buildPocketBoxVoxelGrid } from '@/domain/pockets/pocket-preview'
import type { VisualizationScene } from '@/domain/tasks'
import type {
  PocketSummary,
  ProteinDetail,
  ProteinStructureDetail,
  TargetSummary,
} from '@/types/targets'
import type { ResearchProject } from '@/types/projects'
import type { DesignPocketSelection, DesignStructureSelection } from '@/types/design'

/**
 * 三维预览按需加载：`MoleculeViewer` 会拉起 Mol* 整套渲染栈，
 * 而大部分用户只关心口袋选择本身——没开 `showPreview` 时不该把这部分打进首屏。
 */
const PocketPreviewViewer = defineAsyncComponent(
  () => import('@/components/tasks/MoleculeViewer.vue')
)

const props = withDefaults(
  defineProps<{
    modelValue: DesignPocketSelection | null
    defaultProjectId?: string
    /** 外部受控项目 ID（隐藏内置项目选择器时与外层统一项目同步）。 */
    projectId?: string
    hideProjectSelect?: boolean
    hidePocketSelect?: boolean
    /** 是否在口袋选定后展示紧凑的三维预览（默认关闭，保持既有调用方行为）。 */
    showPreview?: boolean
  }>(),
  {
    defaultProjectId: '',
    projectId: '',
    hideProjectSelect: false,
    hidePocketSelect: false,
    showPreview: false
  }
)

/**
 * Mol* 的 `BuiltInTrajectoryFormat` 用 `mmcif` 表示 CIF / MMCIF，
 * 不能写成 `'cif'`（会破坏 `VisualizationSceneEntry.format` 的类型）。
 */
interface PocketPreviewFormat {
  format: 'pdb' | 'mmcif'
  extension: string
}

const POCKET_PREVIEW_FORMAT_BY_EXTENSION: Record<string, PocketPreviewFormat> = {
  '.pdb': { format: 'pdb', extension: '.pdb' },
  '.ent': { format: 'pdb', extension: '.pdb' },
  '.cif': { format: 'mmcif', extension: '.cif' },
  '.mmcif': { format: 'mmcif', extension: '.mmcif' },
}

/** 从 URN（`file:<id>.pdb` / `s3://bucket/x.cif`）里取小写扩展名；取不到返回空串。 */
function urnExtension(urn: string): string {
  const base = (urn.split('?')[0] || '').split('#')[0] || ''
  const index = base.lastIndexOf('.')
  return index > 0 ? base.slice(index).toLowerCase() : ''
}

const emit = defineEmits<{
  (event: 'update:modelValue', value: DesignPocketSelection | null): void
  (event: 'structure-change', value: DesignStructureSelection | null): void
}>()

const { t } = useI18n()

const projects = ref<ResearchProject[]>([])
const targets = ref<TargetSummary[]>([])
const proteins = ref<ProteinDetail[]>([])
const structures = ref<ProteinStructureDetail[]>([])
const pockets = ref<PocketSummary[]>([])

/**
 * 预览用的结构 URN：优先用选择时携带的 `structureUrn`，否则回查当前结构。
 * 有准备产物时以准备结构的 URN 为准（与 `structureFileId` 的取值口径一致）。
 */
function resolveStructureUrn(): string | null {
  const direct = props.modelValue?.structureUrn
  if (direct) return direct
  const structure = structures.value.find(item => item.id === props.modelValue?.structureId)
  if (!structure) return null
  if (structure.prepared_file_id) {
    return structure.prepared_urn ?? structure.structure_urn ?? null
  }
  return structure.structure_urn ?? structure.prepared_urn ?? null
}

const resolvedFilenames = ref<Record<string, string>>({})
const filenameSequences = new Map<string, ReturnType<typeof useRequestSequence>>()
function filenameSequence(fileId: string) {
  let sequence = filenameSequences.get(fileId)
  if (!sequence) {
    sequence = useRequestSequence()
    filenameSequences.set(fileId, sequence)
  }
  return sequence
}

watch(
  [() => props.showPreview, () => props.modelValue?.structureFileId, () => resolveStructureUrn()],
  async ([enabled, fileId, urn]) => {
    if (!enabled || !fileId || (urn && urnExtension(urn))) return
    const sequence = filenameSequence(fileId)
    const seq = sequence.next()
    try {
      const response = await getFileInfo(fileId)
      if (sequence.isCurrent(seq) && props.modelValue?.structureFileId === fileId && response.data?.filename) {
        resolvedFilenames.value = { ...resolvedFilenames.value, [fileId]: response.data.filename }
      }
    } catch {
      // Do not cache transient lookup failures as an empty filename; a later watch can retry.
      if (sequence.isCurrent(seq) && props.modelValue?.structureFileId === fileId) {
        delete resolvedFilenames.value[fileId]
      }
    }
  },
  { immediate: true }
)

const previewScene = computed<VisualizationScene | null>(() => {
  const fileId = props.modelValue?.structureFileId
  if (!fileId) return null
  const urn = resolveStructureUrn()
  const directExt = urn ? urnExtension(urn) : ''
  // 真实库里的 URN 形如 `file:<uuid>`（无扩展名），此时回退查文件元数据里的原始文件名。
  const effectiveExt = directExt || urnExtension(resolvedFilenames.value[fileId] ?? '')
  const detected = effectiveExt ? POCKET_PREVIEW_FORMAT_BY_EXTENSION[effectiveExt] : undefined
  // 识别不了格式时不要按 PDB 硬渲染——Mol* 会把 CIF 当 PDB 解析出错误结构。
  if (!detected) return null
  const entry = {
    key: `pocket-preview-${fileId}`,
    url: `/api/v1/files/${encodeURIComponent(fileId)}/download`,
    label: props.modelValue?.pocketLabel || 'pocket structure',
    source: 'input' as const,
    role: 'receptor' as const,
    format: detected.format,
    extension: detected.extension,
  }
  return {
    entries: [entry],
    inputEntries: [entry],
    outputEntries: [],
    supportedOutputFiles: [],
    unsupportedOutputFiles: [],
    hasRenderableOutput: true,
    selectedOutputKey: entry.key,
  }
})

const previewVoxelGrid = computed(() =>
  buildPocketBoxVoxelGrid(props.modelValue?.center, props.modelValue?.boxSize)
)

/** 预览不可用时区分「没有结构文件」与「格式无法识别」，避免笼统的失败文案。 */
const previewFallbackMessage = computed(() =>
  props.modelValue?.structureFileId
    ? t('design.molecule.pocketPreviewUnsupportedFormat')
    : t('design.molecule.pocketPreviewMissing')
)

const selectedProject = ref<string | undefined>(props.modelValue?.projectId)
const selectedTarget = ref<string | undefined>(props.modelValue?.targetId)
const selectedProtein = ref<string | undefined>(props.modelValue?.proteinId)
const selectedStructure = ref<string | undefined>(props.modelValue?.structureId)
const selectedPocket = ref<string | undefined>(props.modelValue?.pocketId)
const structureSnapshot = ref<string[]>([])

const loadingProjects = ref(false)
const loadingTargets = ref(false)
const loadingProteins = ref(false)
const loadingStructures = ref(false)
const loadingPockets = ref(false)
const projectSequence = useRequestSequence()
const targetSequence = useRequestSequence()
const proteinSequence = useRequestSequence()
const structureSequence = useRequestSequence()
const pocketSequence = useRequestSequence()
const predictedSequence = useRequestSequence()
const relaySequence = useRequestSequence()
const error = ref('')

const currentStep = computed(() => {
  const stepIndex = !selectedProject.value
    ? 0
    : !selectedTarget.value
      ? 1
      : !selectedProtein.value
        ? 2
        : !selectedStructure.value
          ? 3
          : !selectedPocket.value
            ? 4
            : 5
  return props.hideProjectSelect ? Math.max(0, stepIndex - 1) : stepIndex
})

function structureLabel(structure: ProteinStructureDetail, index: number): string {
  return structure.source_type ? `${structure.source_type} · ${index + 1}` : `#${index + 1}`
}

function pocketLabel(pocket: PocketSummary): string {
  const rank = pocket.rank === null ? '-' : `#${pocket.rank}`
  const score = pocket.score === null ? '' : ` · ${pocket.score.toFixed(3)}`
  return `${rank}${score}`
}

function clearBelow(level: 'target' | 'protein' | 'structure' | 'pocket'): void {
  if (level === 'target') {
    targets.value = []
    selectedTarget.value = undefined
    loadingTargets.value = false
  }
  if (level === 'target' || level === 'protein') {
    proteins.value = []
    selectedProtein.value = undefined
    loadingProteins.value = false
  }
  if (level !== 'pocket') {
    structures.value = []
    selectedStructure.value = undefined
    loadingStructures.value = false
    emit('structure-change', null)
  }
  pockets.value = []
  selectedPocket.value = undefined
  loadingPockets.value = false
  emit('update:modelValue', null)
}

function emitStructureSelection(structureId: string): void {
  if (!selectedProject.value || !selectedTarget.value || !selectedProtein.value) {
    emit('structure-change', null)
    return
  }
  const structure = structures.value.find(item => item.id === structureId)
  if (!structure) {
    emit('structure-change', null)
    return
  }
  emit('structure-change', {
    projectId: selectedProject.value,
    targetId: selectedTarget.value,
    proteinId: selectedProtein.value,
    structureId: structure.id,
    structureFileId: structure.prepared_file_id ?? structure.structure_file_id ?? null,
    structureUrn: structure.prepared_file_id
      ? structure.prepared_urn ?? structure.structure_urn ?? null
      : structure.structure_urn ?? structure.prepared_urn ?? null,
  })
}

function emitPocketSelection(pocket: PocketSummary): void {
  if (
    !selectedProject.value ||
    !selectedTarget.value ||
    !selectedProtein.value ||
    !selectedStructure.value
  ) {
    emit('update:modelValue', null)
    return
  }
  const structure = structures.value.find(item => item.id === selectedStructure.value)
  emit('update:modelValue', {
    projectId: selectedProject.value,
    targetId: selectedTarget.value,
    proteinId: selectedProtein.value,
    structureId: selectedStructure.value,
    pocketId: pocket.id,
    pocketLabel: pocketLabel(pocket),
    score: pocket.score,
    structureFileId: structure?.prepared_file_id ?? structure?.structure_file_id ?? null,
    structureUrn: structure
      ? structure.prepared_file_id
        ? structure.prepared_urn ?? structure.structure_urn ?? null
        : structure.structure_urn ?? structure.prepared_urn ?? null
      : null,
    center: pocket.center ?? null,
    boxSize: pocket.box_size ?? null,
  })
}

async function loadProjects(): Promise<void> {
  const seq = projectSequence.next()
  loadingProjects.value = true
  error.value = ''
  try { const items = await listDesignProjects(); if (projectSequence.isCurrent(seq)) projects.value = items }
  catch { if (projectSequence.isCurrent(seq)) error.value = t('design.pocket.loadFailed') }
  finally { if (projectSequence.isCurrent(seq)) loadingProjects.value = false }
}

async function handleProjectChange(value: unknown): Promise<void> {
  targetSequence.invalidate(); proteinSequence.invalidate(); structureSequence.invalidate(); pocketSequence.invalidate(); predictedSequence.invalidate(); relaySequence.invalidate()
  clearBelow('target')
  if (typeof value !== 'string') return
  const seq = targetSequence.next(); loadingTargets.value = true
  try { const items = await listProjectTargets(value); if (targetSequence.isCurrent(seq) && selectedProject.value === value) targets.value = items }
  catch { if (targetSequence.isCurrent(seq) && selectedProject.value === value) error.value = t('design.pocket.loadFailed') }
  finally { if (targetSequence.isCurrent(seq) && selectedProject.value === value) loadingTargets.value = false }
}

async function handleTargetChange(value: unknown): Promise<void> {
  proteinSequence.invalidate(); structureSequence.invalidate(); pocketSequence.invalidate(); predictedSequence.invalidate(); relaySequence.invalidate()
  clearBelow('protein')
  if (typeof value !== 'string') return
  const seq = proteinSequence.next(); loadingProteins.value = true
  try { const items = await loadTargetProteins(value); if (proteinSequence.isCurrent(seq) && selectedTarget.value === value) proteins.value = items }
  catch { if (proteinSequence.isCurrent(seq) && selectedTarget.value === value) error.value = t('design.pocket.loadFailed') }
  finally { if (proteinSequence.isCurrent(seq) && selectedTarget.value === value) loadingProteins.value = false }
}

async function handleProteinChange(value: unknown): Promise<void> {
  structureSequence.invalidate(); pocketSequence.invalidate(); predictedSequence.invalidate(); relaySequence.invalidate()
  clearBelow('structure')
  if (typeof value !== 'string') return
  const seq = structureSequence.next(); loadingStructures.value = true
  try { const items = await listProteinStructures(value); if (structureSequence.isCurrent(seq) && selectedProtein.value === value) structures.value = items }
  catch { if (structureSequence.isCurrent(seq) && selectedProtein.value === value) error.value = t('design.pocket.loadFailed') }
  finally { if (structureSequence.isCurrent(seq) && selectedProtein.value === value) loadingStructures.value = false }
}

async function loadPocketsForStructure(structureId: string): Promise<void> {
  const seq = pocketSequence.next(); loadingPockets.value = true; pockets.value = []; selectedPocket.value = undefined
  try { const all = await listStructurePockets(structureId); if (pocketSequence.isCurrent(seq) && selectedStructure.value === structureId) pockets.value = all.filter(pocket => pocket.selected) }
  catch { if (pocketSequence.isCurrent(seq) && selectedStructure.value === structureId) error.value = t('design.pocket.loadFailed') }
  finally { if (pocketSequence.isCurrent(seq) && selectedStructure.value === structureId) loadingPockets.value = false }
}

async function handleStructureChange(value: unknown): Promise<void> {
  pocketSequence.invalidate(); relaySequence.invalidate(); clearBelow('pocket')
  if (typeof value !== 'string') {
    emit('structure-change', null)
    return
  }
  emitStructureSelection(value)
  await loadPocketsForStructure(value)
}

function snapshotStructures(): void { structureSnapshot.value = structures.value.map(structure => structure.id) }

async function handleStructurePredicted(): Promise<void> {
  const proteinId = selectedProtein.value
  if (!proteinId) return
  const seq = predictedSequence.next(); loadingStructures.value = true
  try { const fresh = await listProteinStructures(proteinId); if (!predictedSequence.isCurrent(seq) || selectedProtein.value !== proteinId) return; structures.value = fresh; const added = selectNewlyAdded(structureSnapshot.value, fresh); if (added) { selectedStructure.value = added.id; emitStructureSelection(added.id); await loadPocketsForStructure(added.id) } }
  catch { if (predictedSequence.isCurrent(seq)) error.value = t('design.pocket.loadFailed') }
  finally { if (predictedSequence.isCurrent(seq)) loadingStructures.value = false }
}

async function handleRelayPocketSelected(pocket: PocketSummary): Promise<void> {
  const structureId = selectedStructure.value
  if (!structureId) return
  const seq = relaySequence.next()
  try { const all = await listStructurePockets(structureId); if (!relaySequence.isCurrent(seq) || selectedStructure.value !== structureId) return; pockets.value = all.filter(item => item.selected); const chosen = pockets.value.find(item => item.id === pocket.id) ?? pockets.value[0]; if (chosen) { selectedPocket.value = chosen.id; emitPocketSelection(chosen) } }
  catch { if (relaySequence.isCurrent(seq) && selectedStructure.value === structureId) error.value = t('design.pocket.loadFailed') }
}

function onRelayPredicted(): void { error.value = '' }
function onRelayError(message: string): void { error.value = message || t('design.pocket.loadFailed') }

function handlePocketChange(value: unknown): void {
  if (typeof value !== 'string') { emit('update:modelValue', null); return }
  const pocket = pockets.value.find(item => item.id === value)
  if (!pocket) { emit('update:modelValue', null); return }
  emitPocketSelection(pocket)
}

watch(
  () => props.projectId,
  nextProjectId => {
    if (!props.hideProjectSelect) return
    const normalized = nextProjectId || undefined
    if (normalized === selectedProject.value) return
    selectedProject.value = normalized
    void handleProjectChange(normalized)
  }
)

onMounted(async () => {
  await loadProjects()
  const initialProject = props.projectId || props.defaultProjectId
  if (!selectedProject.value && initialProject) {
    selectedProject.value = initialProject
    await handleProjectChange(initialProject)
  }
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.pocket-stepper {
  margin-bottom: @spacing-lg;

  :deep(.ant-steps-item-title) {
    font-size: @font-size-xs;
    white-space: nowrap;
  }
}

.relay-panel {
  margin-top: @spacing-md;
  padding: @spacing-md;
  border: 1px solid @accent-color-border;
  border-radius: @border-radius-md;
  background: @accent-color-light;
}

.relay-title {
  margin-bottom: @spacing-sm;
  color: @accent-color;
  font-size: @font-size-sm;
  font-weight: @font-weight-medium;
}

.pocket-picker__hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: @warning-color;
}

.pocket-preview {
  margin-top: @spacing-md;
  padding: @spacing-md;
  border: 1px solid @border-color;
  border-radius: @border-radius-md;
  background: @surface-sunken;
}

.pocket-preview__title {
  margin-bottom: @spacing-sm;
  color: @text-secondary;
  font-size: @font-size-sm;
  font-weight: @font-weight-medium;
}

.pocket-preview__viewer {
  height: 240px;
  overflow: hidden;
  border-radius: @border-radius-md;
}

.pocket-preview__empty {
  padding: @spacing-lg;
  color: @text-tertiary;
  font-size: @font-size-sm;
  text-align: center;
}
</style>
