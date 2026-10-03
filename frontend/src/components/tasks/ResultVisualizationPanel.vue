<template>
  <div
    v-if="hasVisualizationContent"
    class="result-visualization-panel"
    :class="`result-visualization-panel--${variant}`"
  >
    <div v-if="!isCompact" class="panel-header">
      <div>
        <h4>{{ t('tasks.resultVisualization') }}</h4>
        <p>{{ panelDescription }}</p>
      </div>
      <a-tag v-if="resultItems.length" color="blue">
        {{ resultItems.length }} {{ t('tasks.visualizationFiles') }}
      </a-tag>
    </div>

    <div v-if="resultItems.length" class="visualization-browser">
      <nav class="visualization-result-list" :aria-label="t('tasks.visualizationResultList')">
        <button
          v-for="(item, index) in resultItems"
          :key="item.key"
          :data-testid="'visualization-result-item'"
          :data-result-kind="item.kind"
          type="button"
          class="visualization-result-item"
          :class="{ 'visualization-result-item--active': selectedResult?.key === item.key }"
          :aria-current="selectedResult?.key === item.key ? 'true' : undefined"
          @click="selectResult(item.key)"
        >
          <span class="visualization-result-item__index">{{ index + 1 }}</span>
          <span class="visualization-result-item__meta">
            <span class="visualization-result-item__name">{{ item.label }}</span>
            <span class="visualization-result-item__desc">{{ item.description }}</span>
          </span>
        </button>
      </nav>

      <section class="visualization-preview" aria-live="polite">
        <div class="visualization-preview__toolbar">
          <button
            data-testid="visualization-result-previous"
            type="button"
            class="visualization-preview__arrow"
            :disabled="!hasPreviousResult"
            :aria-label="t('tasks.visualizationPrevious')"
            @click="selectAdjacentResult(-1)"
          >
            <ArrowLeftOutlined />
          </button>
          <span data-testid="visualization-result-position" class="visualization-preview__position">
            {{ selectedResultIndex + 1 }} / {{ resultItems.length }}
          </span>
          <button
            data-testid="visualization-result-next"
            type="button"
            class="visualization-preview__arrow"
            :disabled="!hasNextResult"
            :aria-label="t('tasks.visualizationNext')"
            @click="selectAdjacentResult(1)"
          >
            <ArrowRightOutlined />
          </button>
        </div>

        <div class="visualization-preview__body">
          <MoleculeViewer
            v-if="selectedResult?.kind === 'structure'"
            :scene="focusedScene"
            :variant="variant"
            :allow-native-fullscreen="allowNativeFullscreen"
          />
          <CsvResultViewer
            v-else-if="selectedResult?.kind === 'csv' && selectedResult.file"
            :file="selectedResult.file"
          />
          <ResultFilePreview
            v-else-if="selectedResult?.kind === 'file' && selectedResult.file && selectedResult.previewKind"
            :file="selectedResult.file"
            :preview-kind="selectedResult.previewKind"
          />
          <ArtifactRenderer
            v-else-if="selectedResult?.kind === 'artifact' && selectedResult.artifact"
            :artifact="selectedResult.artifact"
          />
        </div>
      </section>
    </div>

    <a-alert
      v-else
      type="info"
      show-icon
      :message="t('tasks.visualizationUnsupported')"
      :description="t('tasks.visualizationUnsupportedDesc')"
    />

    <div
      v-if="!isCompact && selectedResult?.kind === 'structure' && focusedScene.hasRenderableOutput"
      class="scene-files"
    >
      <div
        v-for="entry in focusedScene.entries"
        :key="entry.key"
        class="scene-file"
        :class="[`scene-file--${entry.source}`]"
      >
        <span class="scene-file__extension">{{ entry.extension.replace('.', '').toUpperCase() }}</span>
        <span class="scene-file__label">{{ entry.label }}</span>
      </div>
    </div>

    <div
      v-if="downloadOnlyResultCount && !isCompact"
      class="download-only-note"
    >
      {{ t('tasks.visualizationDownloadOnlyHint', { count: downloadOnlyResultCount }) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowLeftOutlined, ArrowRightOutlined } from '@ant-design/icons-vue'

import type { Task } from '@/types/models'
import type { TypedArtifact } from '@/types/artifacts'

import ArtifactRenderer from '@/components/artifacts/ArtifactRenderer.vue'
import CsvResultViewer from './CsvResultViewer.vue'
import MoleculeViewer from './MoleculeViewer.vue'
import ResultFilePreview from './ResultFilePreview.vue'
import {
  buildFocusedVisualizationScene,
  buildVisualizationScene,
  buildVisualizationResultItems,
  createVisualizationScene,
  preferTopRankedSdfFiles
} from '@/domain/tasks'

const props = withDefaults(defineProps<{
  task: Task
  variant?: 'compact' | 'full'
  allowNativeFullscreen?: boolean
}>(), {
  variant: 'full',
  allowNativeFullscreen: true,
})

const { t } = useI18n()
const isCompact = computed(() => props.variant === 'compact')

const hasOutputFiles = computed(() => Boolean(props.task.output_files?.length))
const typedArtifacts = computed<TypedArtifact[]>(() => props.task.artifacts ?? [])
const preferredTask = computed(() => ({
  ...props.task,
  output_files: preferTopRankedSdfFiles(props.task.output_files)
}))
const baseScene = computed(() => buildVisualizationScene(preferredTask.value))
const scene = computed(() => baseScene.value)

const resultItems = computed(() => buildVisualizationResultItems(props.task, scene.value))
const downloadOnlyResultCount = computed(() => resultItems.value.filter(item => (
  item.kind === 'file' && item.previewKind === 'download'
)).length)
const selectedResultKey = ref<string | null>(null)
const selectedResult = computed(() =>
  resultItems.value.find(item => item.key === selectedResultKey.value) || resultItems.value[0] || null
)
const selectedResultIndex = computed(() => {
  const index = resultItems.value.findIndex(item => item.key === selectedResult.value?.key)
  return index >= 0 ? index : 0
})
const hasPreviousResult = computed(() => selectedResultIndex.value > 0)
const hasNextResult = computed(() => selectedResultIndex.value < resultItems.value.length - 1)
const hasVisualizationContent = computed(() => (
  resultItems.value.length > 0 ||
  typedArtifacts.value.length > 0 ||
  hasOutputFiles.value
))

const focusedScene = computed(() => {
  const selected = selectedResult.value
  if (selected?.kind !== 'structure' || !selected.entry) {
    return createVisualizationScene([], [], [])
  }

  const isOutputEntry = scene.value.outputEntries.some(entry => entry.key === selected.entry?.key)
  if (isOutputEntry) {
    return buildFocusedVisualizationScene(scene.value, selected.entry.key)
  }

  return createVisualizationScene([], [selected.entry], [])
})

function selectResult(key: string) {
  selectedResultKey.value = key
}

function selectAdjacentResult(offset: number) {
  const nextIndex = selectedResultIndex.value + offset
  const nextItem = resultItems.value[nextIndex]
  if (!nextItem) {
    return
  }

  selectResult(nextItem.key)
}

watch(
  () => resultItems.value.map(item => item.key).join('|'),
  () => {
    if (!resultItems.value.some(item => item.key === selectedResultKey.value)) {
      selectedResultKey.value = resultItems.value[0]?.key || null
    }
  },
  { immediate: true }
)

const panelDescription = computed(() => {
  if (selectedResult.value?.kind === 'csv') {
    return t('tasks.csvVisualizationHint')
  }

  if (selectedResult.value?.kind === 'artifact') {
    return selectedResult.value.description
  }

  if (selectedResult.value?.kind === 'file') {
    return t('tasks.filePreview')
  }

  if (!scene.value.hasRenderableOutput && !resultItems.value.length) {
    return t('tasks.visualizationUnsupportedDesc')
  }

  if (resultItems.value.length > 1) {
    return t('tasks.visualizationSelectableHint')
  }

  const hasInputStructure = focusedScene.value.entries.some(entry => entry.source === 'input')
  const hasLigands = focusedScene.value.entries.some(entry => entry.role === 'ligand')

  if (hasInputStructure && hasLigands) {
    return t('tasks.visualizationHint')
  }

  return t('tasks.visualizationFiles')
})
</script>

<style scoped>
.result-visualization-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 20px;
}

.result-visualization-panel--compact {
  width: 100%;
  height: 100%;
  min-height: 0;
  gap: 0;
  margin-bottom: 0;
}

.result-visualization-panel--full {
  min-height: 0;
}

.result-visualization-panel--compact .visualization-browser {
  height: 100%;
  min-height: 0;
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.panel-header h4 {
  margin: 0 0 6px;
  font-size: 17px;
  font-weight: 600;
  color: #1f2937;
}

.panel-header p {
  margin: 0;
  color: #64748b;
  line-height: 1.6;
}

.visualization-browser {
  display: grid;
  grid-template-columns: minmax(190px, 260px) minmax(0, 1fr);
  gap: 12px;
  min-height: 520px;
}

.visualization-result-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  max-height: 520px;
  padding: 4px;
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: @bg-hover;
}

.visualization-result-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #0f172a;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease;
}

.visualization-result-item:hover,
.visualization-result-item:focus-visible {
  border-color: @accent-color;
  background: @bg-hover;
}

.visualization-result-item--active {
  border-color: #2563eb;
  background: #eef6ff;
}

.visualization-result-item__index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.visualization-result-item__meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.visualization-result-item__name {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
  color: #0f172a;
  word-break: break-word;
}

.visualization-result-item__desc {
  font-size: 12px;
  color: #64748b;
  letter-spacing: 0.04em;
}

.visualization-preview {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: @bg-elevated;
}

.visualization-preview__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 44px;
  padding: 6px 10px;
  border-bottom: 1px solid #e2e8f0;
  background: @bg-hover;
}

.visualization-preview__arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 1px solid #cbd5e1;
  border-radius: 7px;
  background: @bg-elevated;
  color: #1d4ed8;
  cursor: pointer;
}

.visualization-preview__arrow:hover:not(:disabled),
.visualization-preview__arrow:focus-visible:not(:disabled) {
  border-color: @accent-color;
  background: @accent-color-light;
}

.visualization-preview__arrow:disabled {
  color: #94a3b8;
  cursor: not-allowed;
  opacity: 0.55;
}

.visualization-preview__position {
  color: #64748b;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.visualization-preview__body {
  min-width: 0;
  min-height: 0;
  overflow: auto;
}

.result-visualization-panel--compact .visualization-browser {
  grid-template-columns: minmax(132px, 190px) minmax(0, 1fr);
  gap: 8px;
}

.result-visualization-panel--compact .visualization-result-list {
  max-height: none;
  min-height: 0;
}

.result-visualization-panel--compact .visualization-preview {
  min-height: 0;
}

.result-visualization-panel--compact .visualization-preview__body {
  height: 100%;
}

.scene-files {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.scene-file {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 999px;
  background: @bg-hover;
  border: 1px solid #e2e8f0;
  color: #0f172a;
}

.scene-file--input {
  background: rgba(245, 158, 11, 0.12);
  border-color: rgba(245, 158, 11, 0.25);
}

.scene-file--output {
  background: rgba(59, 130, 246, 0.12);
  border-color: rgba(59, 130, 246, 0.25);
}

.scene-file__extension {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #0f766e;
}

.scene-file__label {
  font-size: 13px;
  line-height: 1.4;
}

.download-only-note {
  margin-top: 4px;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  color: #64748b;
  background: #f8fafc;
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 768px) {
  .panel-header {
    flex-direction: column;
  }

  .visualization-browser {
    grid-template-columns: 1fr;
    min-height: 0;
  }

  .visualization-result-list {
    max-height: 180px;
  }
}
</style>
