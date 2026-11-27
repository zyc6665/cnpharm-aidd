<template>
  <div class="pocket-coordinate-panel">
    <div class="pocket-coordinate-panel__header" :data-testid="ids.modeGroup">
      <span class="pocket-coordinate-panel__label">{{ t('design.molecule.pocketDefineMode') }}</span>
      <a-radio-group
        :value="modelValue"
        size="small"
        button-style="solid"
        :disabled="disabled"
        @update:value="handleModeChange"
      >
        <a-radio-button
          v-if="allowProjectMode"
          value="project"
          :data-testid="ids.modeProject"
        >
          {{ t('design.molecule.pocketModeProject') }}
        </a-radio-button>
        <a-radio-button value="ref_ligand" :data-testid="ids.modeRefLigand">
          {{ t('design.molecule.pocketModeRefLigand') }}
        </a-radio-button>
        <a-radio-button value="coords" :data-testid="ids.modeCoords">
          {{ t('design.molecule.pocketModeCoords') }}
        </a-radio-button>
        <a-radio-button value="pocket_file" :data-testid="ids.modeFile">
          {{ t('design.molecule.pocketModeFile') }}
        </a-radio-button>
      </a-radio-group>
    </div>

    <div
      v-if="effectiveMode !== 'project'"
      class="pocket-coordinate-panel__body"
      :data-testid="ids.panel"
    >
      <div v-if="effectiveMode === 'ref_ligand'" class="pocket-coordinate-panel__field">
        <span class="pocket-coordinate-panel__label">{{ t('design.molecule.refLigandFile') }}</span>
        <div class="pocket-coordinate-panel__upload">
          <a-upload
            :show-upload-list="false"
            :before-upload="handleRefLigandFile"
            :disabled="disabled"
            accept=".sdf,.sd,.mol,.mol2,.pdb"
            :data-testid="ids.refLigandUpload"
          >
            <a-button size="small" :disabled="disabled">{{ t('design.molecule.chooseFile') }}</a-button>
          </a-upload>
          <span v-if="refLigandFile" class="pocket-coordinate-panel__file" :data-testid="ids.refLigandName">
            {{ refLigandFile.name }}
          </span>
          <span v-else class="pocket-coordinate-panel__hint">{{ t('design.molecule.refLigandHint') }}</span>
        </div>
        <span
          v-if="refLigandSummaryText"
          class="pocket-coordinate-panel__hint pocket-coordinate-panel__hint--accent"
          :data-testid="ids.refLigandSummary"
        >
          {{ refLigandSummaryText }}
        </span>
      </div>

      <div v-else-if="effectiveMode === 'coords'" class="pocket-coordinate-panel__field">
        <div class="pocket-coordinate-panel__coords-header">
          <span class="pocket-coordinate-panel__label">{{ t('design.molecule.centerCoordsLabel') }}</span>
          <a-button
            v-if="hasAnyManualCoord"
            type="link"
            size="small"
            :disabled="disabled"
            :data-testid="ids.clearCoords"
            @click="clearManualCenter"
          >
            {{ t('design.molecule.clearCoords') }}
          </a-button>
        </div>
        <div class="pocket-coordinate-panel__coords-grid">
          <div class="pocket-coordinate-panel__coord-item">
            <span class="pocket-coordinate-panel__axis">X</span>
            <a-input-number
              v-model:value="manualCenter.x"
              :step="0.5"
              :precision="2"
              :disabled="disabled"
              placeholder="0.00"
              class="pocket-coordinate-panel__number"
              :data-testid="ids.centerX"
            />
          </div>
          <div class="pocket-coordinate-panel__coord-item">
            <span class="pocket-coordinate-panel__axis">Y</span>
            <a-input-number
              v-model:value="manualCenter.y"
              :step="0.5"
              :precision="2"
              :disabled="disabled"
              placeholder="0.00"
              class="pocket-coordinate-panel__number"
              :data-testid="ids.centerY"
            />
          </div>
          <div class="pocket-coordinate-panel__coord-item">
            <span class="pocket-coordinate-panel__axis">Z</span>
            <a-input-number
              v-model:value="manualCenter.z"
              :step="0.5"
              :precision="2"
              :disabled="disabled"
              placeholder="0.00"
              class="pocket-coordinate-panel__number"
              :data-testid="ids.centerZ"
            />
          </div>
        </div>
        <span class="pocket-coordinate-panel__hint">{{ t('design.molecule.centerCoordsHint') }}</span>
      </div>

      <div v-else class="pocket-coordinate-panel__field">
        <span class="pocket-coordinate-panel__label">{{ t('design.molecule.pocketFile') }}</span>
        <div class="pocket-coordinate-panel__upload">
          <a-upload
            :show-upload-list="false"
            :before-upload="handlePocketFile"
            :disabled="disabled"
            accept=".pdb"
            :data-testid="ids.pocketUpload"
          >
            <a-button size="small" :disabled="disabled">{{ t('design.molecule.chooseFile') }}</a-button>
          </a-upload>
          <span v-if="pocketFile" class="pocket-coordinate-panel__file" :data-testid="ids.pocketName">
            {{ pocketFile.name }}
          </span>
          <span v-else class="pocket-coordinate-panel__hint">{{ t('design.molecule.pocketFileHint') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useRequestSequence } from '@/composables/useRequestSequence'
import { parseAndNormalizeLigandUpload } from '@/domain/molecules/ligand-upload'
import { parsePocketGeometry, parseReferenceLigandGeometry } from '@/domain/pockets/pocket-geometry'

export type PocketDefineMode = 'project' | 'ref_ligand' | 'coords' | 'pocket_file'

export interface PocketTestIds {
  modeGroup?: string
  modeProject?: string
  modeRefLigand?: string
  modeCoords?: string
  modeFile?: string
  panel?: string
  refLigandUpload?: string
  refLigandName?: string
  refLigandSummary?: string
  centerX?: string
  centerY?: string
  centerZ?: string
  clearCoords?: string
  pocketUpload?: string
  pocketName?: string
}

export interface PocketCoordinateState {
  mode: PocketDefineMode
  center: { x: number; y: number; z: number } | null
  boxSize: { x: number; y: number; z: number } | null
  label: string
  parsing: boolean
  hasAnyInput: boolean
  refLigandFile: File | null
  refLigandUpload: File | null
  pocketFile: File | null
}

const props = withDefaults(
  defineProps<{
    modelValue: PocketDefineMode
    allowProjectMode?: boolean
    disabled?: boolean
    testIds?: PocketTestIds
  }>(),
  {
    allowProjectMode: false,
    disabled: false,
    testIds: () => ({})
  }
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: PocketDefineMode): void
  (event: 'change', state: PocketCoordinateState): void
}>()

const { t } = useI18n()

const ids = computed(() => ({
  modeGroup: props.testIds.modeGroup ?? 'molecule-pocket-mode',
  modeProject: props.testIds.modeProject ?? 'molecule-pocket-mode-project',
  modeRefLigand: props.testIds.modeRefLigand ?? 'molecule-pocket-mode-ligand',
  modeCoords: props.testIds.modeCoords ?? 'molecule-pocket-mode-coords',
  modeFile: props.testIds.modeFile ?? 'molecule-pocket-mode-file',
  panel: props.testIds.panel ?? 'molecule-custom-pocket-panel',
  refLigandUpload: props.testIds.refLigandUpload ?? 'molecule-upload-ref-ligand',
  refLigandName: props.testIds.refLigandName ?? 'molecule-upload-ref-ligand-name',
  refLigandSummary: props.testIds.refLigandSummary ?? 'molecule-ref-ligand-summary',
  centerX: props.testIds.centerX ?? 'molecule-center-x',
  centerY: props.testIds.centerY ?? 'molecule-center-y',
  centerZ: props.testIds.centerZ ?? 'molecule-center-z',
  clearCoords: props.testIds.clearCoords ?? 'molecule-clear-coords',
  pocketUpload: props.testIds.pocketUpload ?? 'molecule-upload-pocket',
  pocketName: props.testIds.pocketName ?? 'molecule-upload-pocket-name'
}))

const effectiveMode = computed<PocketDefineMode>(() =>
  !props.allowProjectMode && props.modelValue === 'project' ? 'ref_ligand' : props.modelValue
)

const pocketFile = ref<File | null>(null)
const pocketCenter = ref<{ x: number; y: number; z: number } | null>(null)
const pocketBoxSize = ref<{ x: number; y: number; z: number } | null>(null)
const pocketParsing = ref(false)
const pocketSequence = useRequestSequence()
let parsedPocketFile: File | null = null

const refLigandFile = ref<File | null>(null)
const refLigandUpload = ref<File | null>(null)
const refLigandCenter = ref<{ x: number; y: number; z: number } | null>(null)
const refLigandBoxSize = ref<{ x: number; y: number; z: number } | null>(null)
const refLigandAtomCount = ref<number | null>(null)
const refLigandParsing = ref(false)
const refLigandSequence = useRequestSequence()
let parsedRefLigandFile: File | null = null

const manualCenter = reactive<{ x: number | null; y: number | null; z: number | null }>({
  x: null,
  y: null,
  z: null
})
const hasAnyManualCoord = computed(() =>
  manualCenter.x !== null || manualCenter.y !== null || manualCenter.z !== null
)
const manualCenterReady = computed(() =>
  manualCenter.x !== null &&
  manualCenter.y !== null &&
  manualCenter.z !== null &&
  Number.isFinite(manualCenter.x) &&
  Number.isFinite(manualCenter.y) &&
  Number.isFinite(manualCenter.z)
)

const refLigandSummaryText = computed(() => {
  if (!refLigandCenter.value || refLigandAtomCount.value === null) return ''
  return t('design.molecule.refLigandParsed', {
    count: refLigandAtomCount.value,
    x: refLigandCenter.value.x.toFixed(2),
    y: refLigandCenter.value.y.toFixed(2),
    z: refLigandCenter.value.z.toFixed(2)
  })
})

const currentState = computed<PocketCoordinateState>(() => {
  const mode = effectiveMode.value
  const center =
    mode === 'ref_ligand'
      ? refLigandCenter.value
      : mode === 'coords' && manualCenterReady.value
        ? { x: manualCenter.x!, y: manualCenter.y!, z: manualCenter.z! }
        : mode === 'pocket_file'
          ? pocketCenter.value
          : null
  const boxSize =
    mode === 'ref_ligand'
      ? refLigandBoxSize.value
      : mode === 'coords' && manualCenterReady.value
        ? { x: 20, y: 20, z: 20 }
        : mode === 'pocket_file'
          ? pocketBoxSize.value
          : null
  const label =
    mode === 'ref_ligand'
      ? refLigandFile.value?.name || '-'
      : mode === 'coords'
        ? manualCenterReady.value ? t('design.molecule.pocketModeCoords') : '-'
        : mode === 'pocket_file'
          ? pocketFile.value?.name || '-'
          : '-'
  return {
    mode,
    center,
    boxSize,
    label,
    parsing: pocketParsing.value || refLigandParsing.value,
    hasAnyInput: Boolean(pocketFile.value || refLigandFile.value || hasAnyManualCoord.value),
    refLigandFile: refLigandFile.value,
    refLigandUpload: refLigandUpload.value,
    pocketFile: pocketFile.value
  }
})

watch(
  currentState,
  state => emit('change', state),
  { immediate: true, deep: true, flush: 'sync' }
)

function handleModeChange(next: unknown): void {
  if (next === 'project' || next === 'ref_ligand' || next === 'coords' || next === 'pocket_file') {
    emit('update:modelValue', next)
  }
}

function clearManualCenter(): void {
  manualCenter.x = null
  manualCenter.y = null
  manualCenter.z = null
}

function setCoordinates(center: { x: number; y: number; z: number }): void {
  manualCenter.x = Number(center.x.toFixed(2))
  manualCenter.y = Number(center.y.toFixed(2))
  manualCenter.z = Number(center.z.toFixed(2))
  emit('update:modelValue', 'coords')
}

function setPocketFileState(
  file: File,
  center: { x: number; y: number; z: number },
  boxSize: { x: number; y: number; z: number }
): void {
  pocketFile.value = file
  parsedPocketFile = file
  pocketCenter.value = center
  pocketBoxSize.value = boxSize
  emit('update:modelValue', 'pocket_file')
}

async function handleRefLigandFile(file: File): Promise<boolean> {
  const seq = refLigandSequence.next()
  refLigandFile.value = file
  parsedRefLigandFile = file
  refLigandUpload.value = null
  refLigandCenter.value = null
  refLigandBoxSize.value = null
  refLigandAtomCount.value = null
  refLigandParsing.value = true
  try {
    const text = await file.text()
    if (!refLigandSequence.isCurrent(seq) || parsedRefLigandFile !== file || refLigandFile.value !== file) {
      return false
    }
    const geometry = parseReferenceLigandGeometry(text, file.name)
    const prepared = await parseAndNormalizeLigandUpload(file, text, { convertNonSdfToSdf: true })
    if (!refLigandSequence.isCurrent(seq) || parsedRefLigandFile !== file || refLigandFile.value !== file) {
      return false
    }
    if (!geometry || !prepared) throw new Error('unreadable reference ligand')
    refLigandCenter.value = geometry.center
    refLigandBoxSize.value = geometry.boxSize
    refLigandAtomCount.value = geometry.pointCount
    refLigandUpload.value = prepared.uploadFile
  } catch {
    if (refLigandSequence.isCurrent(seq) && parsedRefLigandFile === file) {
      refLigandFile.value = null
      message.warning(t('design.molecule.refLigandUnreadable'))
    }
  } finally {
    if (refLigandSequence.isCurrent(seq) && parsedRefLigandFile === file) {
      refLigandParsing.value = false
    }
  }
  return false
}

async function handlePocketFile(file: File): Promise<boolean> {
  const seq = pocketSequence.next()
  pocketFile.value = file
  parsedPocketFile = file
  pocketParsing.value = true
  pocketCenter.value = null
  pocketBoxSize.value = null
  try {
    const geometry = parsePocketGeometry(await file.text())
    if (!pocketSequence.isCurrent(seq) || parsedPocketFile !== file || pocketFile.value !== file) {
      return false
    }
    if (!geometry) throw new Error('invalid geometry')
    pocketCenter.value = geometry.center
    pocketBoxSize.value = geometry.boxSize
  } catch {
    if (pocketSequence.isCurrent(seq) && parsedPocketFile === file) {
      pocketFile.value = null
      message.warning(t('design.molecule.pocketFileUnreadable'))
    }
  } finally {
    if (pocketSequence.isCurrent(seq) && parsedPocketFile === file) {
      pocketParsing.value = false
    }
  }
  return false
}

defineExpose({ setCoordinates, clearCoordinates: clearManualCenter, setPocketFileState })
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.pocket-coordinate-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pocket-coordinate-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
}

.pocket-coordinate-panel__body {
  padding: 14px;
  border: 1px dashed @border-color;
  border-radius: @border-radius-md;
  background: @bg-elevated;
}

.pocket-coordinate-panel__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pocket-coordinate-panel__label {
  color: @text-secondary;
  font-size: @font-size-sm;
}

.pocket-coordinate-panel__upload {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.pocket-coordinate-panel__file {
  color: @text-primary;
  font-size: @font-size-sm;
  word-break: break-all;
}

.pocket-coordinate-panel__hint {
  color: @text-tertiary;
  font-size: @font-size-sm;
  line-height: 1.5;

  &--accent {
    color: @accent-color;
  }
}

.pocket-coordinate-panel__coords-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.pocket-coordinate-panel__coords-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;

  @media (max-width: 640px) {
    grid-template-columns: minmax(0, 1fr);
  }
}

.pocket-coordinate-panel__coord-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pocket-coordinate-panel__axis {
  flex-shrink: 0;
  font-size: @font-size-xs;
  font-weight: @font-weight-semibold;
  color: @text-secondary;
}

.pocket-coordinate-panel__number {
  width: 100%;
}
</style>
