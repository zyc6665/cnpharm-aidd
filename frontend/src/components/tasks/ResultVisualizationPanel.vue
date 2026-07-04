<template>
  <div v-if="hasOutputFiles" class="result-visualization-panel">
    <div class="panel-header">
      <div>
        <h4>{{ t('tasks.resultVisualization') }}</h4>
        <p>{{ panelDescription }}</p>
      </div>
      <a-tag v-if="csvResultFile" color="cyan">
        CSV
      </a-tag>
      <a-tag v-else-if="scene.hasRenderableOutput" color="blue">
        {{ scene.outputEntries.length }} {{ t('tasks.visualizationFiles') }}
      </a-tag>
    </div>

    <CsvResultViewer v-if="csvResultFile" :file="csvResultFile" />

    <template v-else-if="scene.hasRenderableOutput">
      <div v-if="scene.outputEntries.length > 1" class="output-browser">
        <div class="output-browser__header">
          <div>
            <h5>{{ t('tasks.visualizationResultList') }}</h5>
            <p>{{ t('tasks.visualizationResultListDesc', { count: scene.outputEntries.length }) }}</p>
          </div>
          <a-tag v-if="focusedScene.inputEntries.length" color="orange">
            {{ t('tasks.visualizationInputPinned') }}
          </a-tag>
        </div>

        <div class="output-browser__list">
          <button
            v-for="(entry, index) in scene.outputEntries"
            :key="entry.key"
            type="button"
            class="output-browser__item"
            :class="{ 'output-browser__item--active': selectedOutputKey === entry.key }"
            @click="selectedOutputKey = entry.key"
          >
            <span class="output-browser__index">{{ index + 1 }}</span>
            <span class="output-browser__meta">
              <span class="output-browser__name">{{ entry.label }}</span>
              <span class="output-browser__desc">
                {{ entry.scoreLabel || entry.extension.replace('.', '').toUpperCase() }}
              </span>
            </span>
          </button>
        </div>
      </div>

      <MoleculeViewer :scene="focusedScene" />
    </template>

    <a-alert
      v-else
      type="info"
      show-icon
      :message="t('tasks.visualizationUnsupported')"
      :description="t('tasks.visualizationUnsupportedDesc')"
    />

    <div v-if="!csvResultFile && scene.hasRenderableOutput" class="scene-files">
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

    <a-alert
      v-if="!csvResultFile && scene.unsupportedOutputFiles.length"
      class="partial-support-alert"
      type="info"
      show-icon
      :message="t('tasks.visualizationPartialSupport')"
      :description="t('tasks.visualizationPartialSupportDesc')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Task } from '@/types/models'

import CsvResultViewer from './CsvResultViewer.vue'
import MoleculeViewer from './MoleculeViewer.vue'
import {
  buildFocusedVisualizationScene,
  buildVisualizationScene,
  createVisualizationScene
} from './result-visualization'
import { detectCsvResultFile } from './csv-result'
import { expandSdfOutputEntries } from './sdf-result'
import {
  detectSdfScoreRankingFile,
  preferTopRankedSdfFiles,
  rankSdfEntriesByScoreFile
} from './sdf-ranking'

const props = defineProps<{
  task: Task
}>()

const { t } = useI18n()

const hasOutputFiles = computed(() => Boolean(props.task.output_files?.length))
const preferredTask = computed(() => ({
  ...props.task,
  output_files: preferTopRankedSdfFiles(props.task.output_files)
}))
const usingTopRankedSdf = computed(() => (
  Boolean(props.task.output_files?.length) &&
  preferredTask.value.output_files !== props.task.output_files
))
const baseScene = computed(() => buildVisualizationScene(preferredTask.value))
const scoreRankingFile = computed(
  () => props.task.output_files?.find(file => detectSdfScoreRankingFile(file)) || null
)
const csvResultFile = computed(() => {
  if (baseScene.value.outputEntries.length) {
    return null
  }

  return props.task.output_files?.find(file => detectCsvResultFile(file)) || null
})
const selectedOutputKey = ref<string | null>(null)
const expandedOutputEntries = ref<typeof baseScene.value.outputEntries | null>(null)
let revokeExpandedOutputs: (() => void) | null = null

function cleanupExpandedOutputs() {
  revokeExpandedOutputs?.()
  revokeExpandedOutputs = null
  expandedOutputEntries.value = null
}

async function hydrateExpandedOutputEntries() {
  cleanupExpandedOutputs()

  const hasSdfOutput = baseScene.value.outputEntries.some(entry => entry.format === 'sdf')
  if (!hasSdfOutput) {
    return
  }

  try {
    const expanded = await expandSdfOutputEntries(baseScene.value.outputEntries)
    const shouldUseExpandedEntries =
      expanded.entries.length !== baseScene.value.outputEntries.length ||
      expanded.entries.some((entry, index) => entry.key !== baseScene.value.outputEntries[index]?.key)
    const rankedEntries = usingTopRankedSdf.value
      ? expanded.entries
      : await rankSdfEntriesByScoreFile(expanded.entries, scoreRankingFile.value)
    const shouldUseRankedEntries =
      rankedEntries.length !== expanded.entries.length ||
      rankedEntries.some((entry, index) => (
        entry.key !== expanded.entries[index]?.key ||
        entry.scoreLabel !== expanded.entries[index]?.scoreLabel
      ))

    if (!shouldUseExpandedEntries && !shouldUseRankedEntries) {
      expanded.revoke()
      return
    }

    expandedOutputEntries.value = rankedEntries
    revokeExpandedOutputs = expanded.revoke
  } catch (error) {
    cleanupExpandedOutputs()
    console.warn('Failed to expand multi-molecule SDF outputs', error)
  }
}

watch(
  () => baseScene.value.outputEntries.map(entry => `${entry.key}:${entry.url}`).join('|'),
  () => {
    void hydrateExpandedOutputEntries()
  },
  { immediate: true }
)

watch(
  () => scoreRankingFile.value ? `${scoreRankingFile.value.id}:${scoreRankingFile.value.url}` : '',
  () => {
    void hydrateExpandedOutputEntries()
  },
)

onUnmounted(() => {
  cleanupExpandedOutputs()
})

const scene = computed(() => {
  const outputEntries = expandedOutputEntries.value?.length
    ? expandedOutputEntries.value
    : baseScene.value.outputEntries

  if (outputEntries === baseScene.value.outputEntries) {
    return baseScene.value
  }

  return createVisualizationScene(
    baseScene.value.inputEntries,
    outputEntries,
    baseScene.value.unsupportedOutputFiles
  )
})

const focusedScene = computed(() => buildFocusedVisualizationScene(scene.value, selectedOutputKey.value))

watch(
  () => [scene.value.selectedOutputKey, scene.value.outputEntries.map(entry => entry.key).join('|')],
  () => {
    const hasSelectedOutput = scene.value.outputEntries.some(entry => entry.key === selectedOutputKey.value)

    if (!hasSelectedOutput) {
      selectedOutputKey.value = scene.value.selectedOutputKey
    }
  },
  { immediate: true }
)

const panelDescription = computed(() => {
  if (csvResultFile.value) {
    return t('tasks.csvVisualizationHint')
  }

  if (!scene.value.hasRenderableOutput) {
    return t('tasks.visualizationUnsupportedDesc')
  }

  if (scene.value.outputEntries.length > 1) {
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

.output-browser {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: 20px;
  background:
    radial-gradient(circle at top right, rgba(56, 189, 248, 0.08), transparent 28%),
    linear-gradient(180deg, @bg-elevated, @bg-hover);
  border: 1px solid #e2e8f0;
}

.output-browser__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.output-browser__header h5 {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.output-browser__header p {
  margin: 0;
  color: #64748b;
  line-height: 1.6;
}

.output-browser__list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}

.output-browser__item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid #dbe4ff;
  border-radius: 16px;
  background: @accent-color-light;
  color: #0f172a;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.output-browser__item:hover {
  border-color: @accent-color;
  background: @bg-hover;
  transform: translateY(-1px);
}

.output-browser__item--active {
  border-color: #2563eb;
  background:
    linear-gradient(180deg, rgba(37, 99, 235, 0.12), rgba(191, 219, 254, 0.26)),
    #eef6ff;
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.12);
}

.output-browser__index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 999px;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}

.output-browser__meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.output-browser__name {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
  color: #0f172a;
  word-break: break-word;
}

.output-browser__desc {
  font-size: 12px;
  color: #64748b;
  letter-spacing: 0.04em;
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

.partial-support-alert {
  margin-top: 4px;
}

@media (max-width: 768px) {
  .panel-header {
    flex-direction: column;
  }

  .output-browser__header {
    flex-direction: column;
  }

  .output-browser__list {
    grid-template-columns: 1fr;
  }
}
</style>
