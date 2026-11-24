<template>
  <div class="pocket-picker" data-testid="pocket-picker">
    <a-steps :current="currentStep" size="small" class="pocket-stepper" data-testid="pocket-stepper">
      <a-step :title="t('design.pocket.project')" />
      <a-step :title="t('design.pocket.target')" />
      <a-step :title="t('design.pocket.protein')" />
      <a-step :title="t('design.pocket.structure')" />
      <a-step :title="t('design.pocket.pocket')" />
    </a-steps>

    <a-spin :spinning="loadingProjects">
      <a-row :gutter="16">
        <a-col :xs="24" :sm="12" :lg="8">
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

        <a-col :xs="24" :sm="12" :lg="8">
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
      <section v-else-if="selectedStructure && !pockets.length" class="relay-panel" data-testid="pocket-missing-pocket">
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
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  listDesignProjects,
  listProjectTargets,
  listProteinStructures,
  listStructurePockets,
  loadTargetProteins,
} from '@/api/design'
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
import type { DesignPocketSelection } from '@/types/design'

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
    /** 是否在口袋选定后展示紧凑的三维预览（默认关闭，保持既有调用方行为）。 */
    showPreview?: boolean
  }>(),
  { defaultProjectId: '', showPreview: false }
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

const previewScene = computed<VisualizationScene | null>(() => {
  const fileId = props.modelValue?.structureFileId
  if (!fileId) return null
  const urn = resolveStructureUrn()
  if (!urn) return null
  const detected = POCKET_PREVIEW_FORMAT_BY_EXTENSION[urnExtension(urn)]
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

const emit = defineEmits<{
  (event: 'update:modelValue', value: DesignPocketSelection | null): void
}>()

const { t } = useI18n()

/** 预览不可用时区分「没有结构文件」与「格式无法识别」，避免笼统的失败文案。 */
const previewFallbackMessage = computed(() =>
  props.modelValue?.structureFileId
    ? t('design.molecule.pocketPreviewUnsupportedFormat')
    : t('design.molecule.pocketPreviewMissing')
)

const projects = ref<ResearchProject[]>([])
const targets = ref<TargetSummary[]>([])
const proteins = ref<ProteinDetail[]>([])
const structures = ref<ProteinStructureDetail[]>([])
const pockets = ref<PocketSummary[]>([])

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
const error = ref('')

const currentStep = computed(() => {
  if (!selectedProject.value) return 0
  if (!selectedTarget.value) return 1
  if (!selectedProtein.value) return 2
  if (!selectedStructure.value) return 3
  if (!selectedPocket.value) return 4
  return 5
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
  }
  if (level === 'target' || level === 'protein') {
    proteins.value = []
    selectedProtein.value = undefined
  }
  if (level !== 'pocket') {
    structures.value = []
    selectedStructure.value = undefined
  }
  pockets.value = []
  selectedPocket.value = undefined
  emit('update:modelValue', null)
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
  loadingProjects.value = true
  error.value = ''
  try {
    projects.value = await listDesignProjects()
  } catch {
    error.value = t('design.pocket.loadFailed')
  } finally {
    loadingProjects.value = false
  }
}

async function handleProjectChange(value: unknown): Promise<void> {
  clearBelow('target')
  if (typeof value !== 'string') {
    return
  }
  loadingTargets.value = true
  try {
    targets.value = await listProjectTargets(value)
  } catch {
    error.value = t('design.pocket.loadFailed')
  } finally {
    loadingTargets.value = false
  }
}

async function handleTargetChange(value: unknown): Promise<void> {
  clearBelow('protein')
  if (typeof value !== 'string') {
    return
  }
  loadingProteins.value = true
  try {
    proteins.value = await loadTargetProteins(value)
  } catch {
    error.value = t('design.pocket.loadFailed')
  } finally {
    loadingProteins.value = false
  }
}

async function handleProteinChange(value: unknown): Promise<void> {
  clearBelow('structure')
  selectedStructure.value = undefined
  structures.value = []
  if (typeof value !== 'string') {
    return
  }
  loadingStructures.value = true
  try {
    structures.value = await listProteinStructures(value)
  } catch {
    error.value = t('design.pocket.loadFailed')
  } finally {
    loadingStructures.value = false
  }
}

async function loadPocketsForStructure(structureId: string): Promise<void> {
  loadingPockets.value = true
  pockets.value = []
  selectedPocket.value = undefined
  try {
    const all = await listStructurePockets(structureId)
    pockets.value = all.filter(pocket => pocket.selected)
  } catch {
    error.value = t('design.pocket.loadFailed')
  } finally {
    loadingPockets.value = false
  }
}

async function handleStructureChange(value: unknown): Promise<void> {
  clearBelow('pocket')
  selectedPocket.value = undefined
  pockets.value = []
  if (typeof value !== 'string') {
    return
  }
  await loadPocketsForStructure(value)
}

function snapshotStructures(): void {
  structureSnapshot.value = structures.value.map(structure => structure.id)
}

async function handleStructurePredicted(): Promise<void> {
  if (!selectedProtein.value) return
  loadingStructures.value = true
  try {
    const fresh = await listProteinStructures(selectedProtein.value)
    structures.value = fresh
    const added = selectNewlyAdded(structureSnapshot.value, fresh)
    if (added) {
      selectedStructure.value = added.id
      await loadPocketsForStructure(added.id)
    }
  } catch {
    error.value = t('design.pocket.loadFailed')
  } finally {
    loadingStructures.value = false
  }
}

async function handleRelayPocketSelected(pocket: PocketSummary): Promise<void> {
  if (!selectedStructure.value) return
  try {
    const all = await listStructurePockets(selectedStructure.value)
    pockets.value = all.filter(item => item.selected)
    const chosen = pockets.value.find(item => item.id === pocket.id) ?? pockets.value[0]
    if (chosen) {
      selectedPocket.value = chosen.id
      emitPocketSelection(chosen)
    }
  } catch {
    error.value = t('design.pocket.loadFailed')
  }
}

function onRelayPredicted(): void {
  error.value = ''
}

function onRelayError(message: string): void {
  error.value = message || t('design.pocket.loadFailed')
}

function handlePocketChange(value: unknown): void {
  if (typeof value !== 'string') {
    emit('update:modelValue', null)
    return
  }
  const pocket = pockets.value.find(item => item.id === value)
  if (!pocket) {
    emit('update:modelValue', null)
    return
  }
  emitPocketSelection(pocket)
}

onMounted(async () => {
  await loadProjects()
  if (!selectedProject.value && props.defaultProjectId) {
    selectedProject.value = props.defaultProjectId
    await handleProjectChange(props.defaultProjectId)
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
