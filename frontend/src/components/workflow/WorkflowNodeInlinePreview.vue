<template>
  <div class="workflow-node-inline-preview">
    <a-empty v-if="!task" class="inline-preview-empty" :description="t('workflow.inlinePreview.empty')" />

    <div v-else-if="isRunning" class="inline-preview-running">
      <div class="inline-preview-status-row">
        <span>{{ t('workflow.inlinePreview.running') }}</span>
        <strong>{{ progress }}%</strong>
      </div>
      <a-progress :percent="progress" size="small" status="active" />
      <p v-if="task.progress_message">{{ task.progress_message }}</p>
    </div>

    <div v-else-if="isFailure" class="inline-preview-error">
      <strong>{{ t('workflow.inlinePreview.failed') }}</strong>
      <p>{{ task.error_message || t('workflow.inlinePreview.failureFallback') }}</p>
    </div>

    <div
      v-else-if="hasOutputs && !selected"
      data-testid="deferred-preview"
      class="inline-preview-deferred"
    >
      <strong>{{ t('workflow.inlinePreview.deferred') }}</strong>
      <span>{{ t('workflow.inlinePreview.outputCount', { count: outputCount }) }}</span>
    </div>

    <div v-else-if="hasOutputs" class="inline-preview-success">
      <div
        class="inline-preview-visualization-shell"
        @pointerdown.stop
        @wheel.stop
      >
        <ResultVisualizationPanel
          :task="visualizationTask"
          variant="compact"
          :allow-native-fullscreen="false"
        />
        <a-button
          class="inline-preview-expand-button"
          size="small"
          shape="circle"
          :title="t('workflow.inlinePreview.expand')"
          :aria-label="t('workflow.inlinePreview.expand')"
          data-placement="top-left"
          data-appearance="light"
          @click.stop="previewOpen = true"
          @pointerdown.stop
        >
          <FullscreenOutlined />
        </a-button>
      </div>
      <a-modal
        v-model:open="previewOpen"
        class="workflow-node-preview-modal"
        wrap-class-name="workflow-node-preview-modal-wrap"
        :title="t('workflow.inlinePreview.previewTitle')"
        :footer="null"
        :width="'min(1120px, 92vw)'"
        :destroy-on-close="true"
      >
        <ResultVisualizationPanel
          v-if="previewOpen"
          :task="visualizationTask"
          variant="full"
          :allow-native-fullscreen="false"
        />
      </a-modal>
    </div>

    <a-empty v-else class="inline-preview-empty" :description="t('workflow.inlinePreview.noPreviewableArtifacts')" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { FullscreenOutlined } from '@ant-design/icons-vue'
import ResultVisualizationPanel from '@/components/tasks/ResultVisualizationPanel.vue'
import { failureStatuses, normalizeTaskStatus, runningStatuses } from '@/domain/tasks'
import type { ArtifactFile, Task } from '@/types/models'

const props = defineProps<{
  selected: boolean
  task?: Task | null
  artifacts?: ArtifactFile[]
}>()

const { t } = useI18n()
const previewOpen = ref(false)

watch(
  () => props.selected,
  (selected) => {
    if (!selected) {
      previewOpen.value = false
    }
  }
)

const taskStatus = computed(() => normalizeTaskStatus(props.task?.status))
const isRunning = computed(() => runningStatuses.includes(taskStatus.value))
const isFailure = computed(() => failureStatuses.includes(taskStatus.value))
const progress = computed(() => Math.max(0, Math.min(100, Number(props.task?.progress ?? 0))))
const outputFiles = computed(() => props.task?.output_files ?? [])
const hasOutputs = computed(() => outputFiles.value.length > 0 || (props.task?.artifacts?.length ?? 0) > 0)
const outputCount = computed(() => outputFiles.value.length + (props.task?.artifacts?.length ?? 0))
const visualizationTask = computed(() => ({
  ...props.task!,
  artifacts: props.task?.artifacts ?? [],
}))
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workflow-node-inline-preview {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  align-items: stretch;
  justify-content: stretch;
  overflow: hidden;
}

.inline-preview-empty,
.inline-preview-running,
.inline-preview-error,
.inline-preview-success,
.inline-preview-output-list {
  width: 100%;
}

.inline-preview-running,
.inline-preview-error,
.inline-preview-deferred,
.inline-preview-output-list {
  display: grid;
  align-content: center;
  gap: @spacing-xs;
  padding: @spacing-sm;
}

.inline-preview-deferred {
  display: grid;
  align-content: center;
  gap: @spacing-xs;
  min-height: 100%;
  padding: @spacing-sm;
  color: @text-color-light-secondary;
  font-size: @font-size-xs;
}

.inline-preview-deferred strong {
  color: @text-color-light-primary;
}

.inline-preview-status-row {
  display: flex;
  justify-content: space-between;
  gap: @spacing-sm;
  color: @text-color-light-secondary;
  font-size: @font-size-xs;
}

.inline-preview-status-row strong {
  color: @text-color-light-primary;
}

.inline-preview-running p,
.inline-preview-error p {
  margin: 0;
  color: @text-color-light-secondary;
  font-size: @font-size-xs;
  line-height: 1.4;
}

.inline-preview-error strong {
  color: @error-color;
  font-size: @font-size-sm;
}

.inline-preview-success {
  min-height: 0;
  overflow: auto;
}

.inline-preview-visualization-shell {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.inline-preview-expand-button {
  position: absolute;
  top: @spacing-xs;
  left: @spacing-xs;
  z-index: 20;
  width: 28px;
  min-width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border-color: @border-color-hover;
  background: @bg-elevated;
  color: @accent-color;
  font-size: @font-size-xs;
  font-weight: 800;
  backdrop-filter: blur(8px);
  box-shadow: @shadow-md;
  pointer-events: auto;
}

.inline-preview-expand-button:hover,
.inline-preview-expand-button:focus-visible {
  border-color: @accent-color;
  background: @bg-surface;
  color: @accent-color-active;
}

.inline-preview-success :deep(.result-visualization-panel) {
  height: 100%;
  min-height: 0;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.inline-preview-success :deep(.result-visualization-panel--compact) {
  padding: 0;
}

.inline-preview-output-title {
  color: @text-color-light-tertiary;
  font-size: @font-size-xs;
  font-weight: 800;
}

.inline-preview-output-chip {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 2px @spacing-xs;
  border: 1px solid @border-color-light;
  border-radius: @border-radius-sm;
  background: @bg-surface;
  color: @text-color-light-secondary;
  font-size: @font-size-xs;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
