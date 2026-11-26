<template>
  <div class="molecule-design-context-panel">
    <!-- Step Readiness Header -->
    <section v-if="steps.length > 0" class="steps-section" data-testid="context-steps">
      <div class="steps-header">
        <div
          v-for="(step, index) in steps"
          :key="step.id"
          class="step-item"
          :class="{ 'is-done': step.done, 'is-active': !step.done && isActiveStep(index) }"
        >
          <div class="step-indicator">
            <check-circle-outlined v-if="step.done" class="step-icon done" />
            <div v-else class="step-number">{{ index + 1 }}</div>
          </div>
          <div class="step-content">
            <div class="step-title">{{ step.title }}</div>
            <div v-if="step.detail" class="step-detail">{{ step.detail }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Live 3D Protein Preview -->
    <section class="preview-section">
      <div class="section-title">{{ previewTitle }}</div>
      <div v-if="previewScene" class="preview-viewer">
        <MoleculeViewer
          :scene="previewScene"
          variant="compact"
          mode="protein"
          :allow-native-fullscreen="false"
        />
      </div>
      <div v-else class="preview-empty">
        <inbox-outlined class="empty-icon" />
        <div class="empty-text">{{ emptyPreviewText }}</div>
      </div>
    </section>

    <!-- Readiness / Missing Checklist -->
    <section class="readiness-section" data-testid="context-readiness">
      <div class="section-title">{{ readinessTitle }}</div>
      <div v-if="canSubmit" class="ready-badge">
        <check-circle-outlined class="ready-icon" />
        <span class="ready-text">{{ readyText }}</span>
      </div>
      <div v-else class="missing-list">
        <div
          v-for="item in missingItems"
          :key="item.id"
          class="missing-item"
          :class="{ 'is-clickable': item.targetTestId }"
          @click="handleMissingItemClick(item)"
        >
          <exclamation-circle-outlined class="missing-icon" />
          <span class="missing-label">{{ item.label }}</span>
        </div>
      </div>
    </section>

    <!-- Live Task Summary Grid -->
    <section class="summary-section">
      <div class="section-title">{{ summaryTitle }}</div>
      <div class="summary-grid">
        <div class="summary-item">
          <div class="summary-label">{{ modelLabel }}</div>
          <div class="summary-value">{{ modelName }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">{{ modeFieldLabel }}</div>
          <div class="summary-value">{{ modeLabel }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">{{ pocketFieldLabel }}</div>
          <div class="summary-value">{{ pocketLabel }}</div>
        </div>
        <div v-if="pocketCenter" class="summary-item">
          <div class="summary-label">{{ pocketCenterLabel }}</div>
          <div class="summary-value">{{ formatPocketCenter }}</div>
        </div>
        <div v-if="pocketBoxSize" class="summary-item">
          <div class="summary-label">{{ pocketBoxLabel }}</div>
          <div class="summary-value">{{ formatPocketBox }}</div>
        </div>
        <div v-if="sampleCount != null" class="summary-item">
          <div class="summary-label">{{ sampleCountLabel }}</div>
          <div class="summary-value">{{ sampleCount }}</div>
        </div>
        <div v-if="fragmentSummary" class="summary-item full-width">
          <div class="summary-label">{{ fragmentLabel }}</div>
          <div class="summary-value">{{ fragmentSummary }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import { CheckCircleOutlined, InboxOutlined, ExclamationCircleOutlined } from '@ant-design/icons-vue'
import type { VisualizationScene } from '@/domain/tasks'
import type { AxisVector } from '@/types/targets'

const MoleculeViewer = defineAsyncComponent(() => import('@/components/tasks/MoleculeViewer.vue'))

export interface ContextStep {
  id: string
  title: string
  done: boolean
  detail?: string
}

export interface MissingItem {
  id: string
  label: string
  targetTestId?: string
}

const props = withDefaults(
  defineProps<{
    modelName: string
    modeLabel: string
    pocketLabel: string
    pocketCenter: AxisVector | null
    pocketBoxSize: AxisVector | null
    previewScene: VisualizationScene | null
    sampleCount?: number | string | null
    fragmentSummary?: string
    steps: ContextStep[]
    missingItems: MissingItem[]
    canSubmit: boolean
  }>(),
  {
    sampleCount: null,
    fragmentSummary: undefined
  }
)

const emit = defineEmits<{
  (event: 'jump-to', targetTestId: string): void
}>()

const { t, te } = useI18n()

const safeT = (key: string, fallback: string): string => {
  return typeof te === 'function' && te(key) ? t(key) : fallback
}

const previewTitle = computed(() => safeT('design.molecule.context.previewTitle', '蛋白结构三维视图'))
const emptyPreviewText = computed(() =>
  safeT('design.molecule.context.previewPlaceholder', '选定项目结构或上传蛋白 PDB 后，这里会实时显示蛋白质三维结构。')
)
const readinessTitle = computed(() =>
  props.canSubmit
    ? safeT('design.molecule.context.panelTitle', '三维上下文与任务就绪状态')
    : safeT('design.molecule.context.readinessMissing', '完成以下项后即可提交：')
)
const readyText = computed(() => safeT('design.molecule.context.readinessReady', '前置项已就绪，可提交任务'))
const summaryTitle = computed(() => safeT('design.molecule.context.summaryTitle', '当前任务摘要'))
const modelLabel = computed(() => safeT('design.molecule.context.summaryModel', '模型'))
const modeFieldLabel = computed(() => safeT('design.molecule.context.summaryMode', '模式'))
const pocketFieldLabel = computed(() => safeT('design.molecule.context.summaryPocket', '口袋'))
const pocketCenterLabel = computed(() => safeT('design.molecule.context.summaryCenter', '中心'))
const pocketBoxLabel = computed(() => safeT('design.molecule.pocketBox', '口袋包围盒'))
const sampleCountLabel = computed(() => safeT('design.molecule.context.summarySamples', '数量'))
const fragmentLabel = computed(() => safeT('design.molecule.context.summaryFragment', '片段 / 原子'))

const isActiveStep = (index: number): boolean => {
  if (index === 0) return true
  return props.steps.slice(0, index).every(step => step.done)
}

const formatPocketCenter = computed(() => {
  if (!props.pocketCenter) return '-'
  const x = props.pocketCenter.x?.toFixed(1) ?? '-'
  const y = props.pocketCenter.y?.toFixed(1) ?? '-'
  const z = props.pocketCenter.z?.toFixed(1) ?? '-'
  return `(${x}, ${y}, ${z}) Å`
})

const formatPocketBox = computed(() => {
  if (!props.pocketBoxSize) return '-'
  const x = props.pocketBoxSize.x?.toFixed(1) ?? '-'
  const y = props.pocketBoxSize.y?.toFixed(1) ?? '-'
  const z = props.pocketBoxSize.z?.toFixed(1) ?? '-'
  return `${x} × ${y} × ${z} Å`
})

const handleMissingItemClick = (item: MissingItem) => {
  if (item.targetTestId) {
    emit('jump-to', item.targetTestId)
  }
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.molecule-design-context-panel {
  display: flex;
  flex-direction: column;
  gap: @spacing-lg;
  background: @bg-elevated;
  border: 1px solid @border-color;
  border-radius: @border-radius-md;
  padding: @spacing-lg;
  height: 100%;
  overflow-y: auto;
}

.section-title {
  font-size: @font-size-sm;
  font-weight: @font-weight-semibold;
  color: @text-secondary;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: @spacing-sm;
}

// Step Readiness Header
.steps-section {
  .steps-header {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .step-item {
    display: flex;
    align-items: flex-start;
    gap: @spacing-sm;
    padding: @spacing-sm;
    border-radius: @border-radius-sm;
    transition: background @transition-base;

    &.is-done {
      .step-indicator {
        color: @success-color;
      }
    }

    &.is-active {
      background: @bg-hover;

      .step-number {
        background: @accent-color;
        color: @text-inverse;
      }
    }
  }

  .step-indicator {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: @text-tertiary;

    .step-icon {
      font-size: 20px;
    }

    .step-number {
      width: 20px;
      height: 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: @bg-surface;
      border-radius: @border-radius-round;
      font-size: @font-size-xs;
      font-weight: @font-weight-semibold;
      color: @text-secondary;
    }
  }

  .step-content {
    flex: 1;
    min-width: 0;
  }

  .step-title {
    font-size: @font-size-sm;
    font-weight: @font-weight-medium;
    color: @text-primary;
  }

  .step-detail {
    font-size: @font-size-xs;
    color: @text-tertiary;
    margin-top: 2px;
  }
}

// Preview Section
.preview-section {
  .preview-viewer {
    border: 1px solid @border-color;
    border-radius: @border-radius-sm;
    overflow: hidden;
    background: @bg-surface;
    height: 280px;
  }

  .preview-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: @spacing-sm;
    padding: @spacing-xl;
    border: 1px dashed @border-color;
    border-radius: @border-radius-sm;
    background: @bg-surface;
    height: 280px;

    .empty-icon {
      font-size: 48px;
      color: @text-tertiary;
      opacity: 0.5;
    }

    .empty-text {
      font-size: @font-size-sm;
      color: @text-tertiary;
      text-align: center;
    }
  }
}

// Readiness Section
.readiness-section {
  .ready-badge {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    padding: @spacing-sm @spacing-md;
    background: @success-bg;
    border: 1px solid @success-color;
    border-radius: @border-radius-sm;

    .ready-icon {
      font-size: 16px;
      color: @success-color;
    }

    .ready-text {
      font-size: @font-size-sm;
      font-weight: @font-weight-medium;
      color: @success-color;
    }
  }

  .missing-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
  }

  .missing-item {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    padding: @spacing-sm @spacing-md;
    background: @warning-bg;
    border: 1px solid @border-color;
    border-radius: @border-radius-sm;
    transition: all @transition-base;

    &.is-clickable {
      cursor: pointer;

      &:hover {
        border-color: @warning-color;
        background: @warning-color-light;
      }
    }

    .missing-icon {
      font-size: 14px;
      color: @warning-color;
      flex-shrink: 0;
    }

    .missing-label {
      font-size: @font-size-sm;
      color: @text-primary;
    }
  }
}

// Summary Section
.summary-section {
  .summary-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: @spacing-md;
  }

  .summary-item {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    padding: @spacing-sm;
    background: @bg-surface;
    border: 1px solid @border-color;
    border-radius: @border-radius-sm;

    &.full-width {
      grid-column: 1 / -1;
    }
  }

  .summary-label {
    font-size: @font-size-xs;
    color: @text-tertiary;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .summary-value {
    font-size: @font-size-sm;
    font-weight: @font-weight-medium;
    color: @text-primary;
    word-break: break-word;
  }
}
</style>
