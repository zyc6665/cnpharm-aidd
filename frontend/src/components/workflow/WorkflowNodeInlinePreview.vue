<template>
  <div class="workflow-node-inline-preview">
    <a-empty v-if="!task" class="inline-preview-empty" description="暂无运行结果" />

    <div v-else-if="isRunning" class="inline-preview-running">
      <div class="inline-preview-status-row">
        <span>运行中</span>
        <strong>{{ progress }}%</strong>
      </div>
      <a-progress :percent="progress" size="small" status="active" />
      <p v-if="task.progress_message">{{ task.progress_message }}</p>
    </div>

    <div v-else-if="isFailure" class="inline-preview-error">
      <strong>运行失败</strong>
      <p>{{ task.error_message || '请查看任务日志定位失败原因。' }}</p>
    </div>

    <div v-else-if="hasOutputs" class="inline-preview-success">
      <template v-if="selected">
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
            title="放大查看"
            aria-label="放大查看"
            data-placement="top-left"
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
          title="结果预览"
          :footer="null"
          :width="'min(1120px, 92vw)'"
          :destroy-on-close="true"
        >
          <ResultVisualizationPanel
            :task="visualizationTask"
            variant="full"
            :allow-native-fullscreen="false"
          />
        </a-modal>
      </template>
      <div v-else class="inline-preview-output-list">
        <span class="inline-preview-output-title">输出产物</span>
        <span
          v-for="file in visibleOutputFiles"
          :key="String(file.id ?? file.filename ?? file.url)"
          class="inline-preview-output-chip"
        >
          {{ file.filename || file.original_name || file.relative_path || 'output' }}
        </span>
        <span v-if="hiddenOutputCount > 0" class="inline-preview-output-chip">
          +{{ hiddenOutputCount }}
        </span>
      </div>
    </div>

    <a-empty v-else class="inline-preview-empty" description="任务已完成，暂无可预览产物" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { FullscreenOutlined } from '@ant-design/icons-vue'
import ResultVisualizationPanel from '@/components/tasks/ResultVisualizationPanel.vue'
import { normalizeTaskStatus } from '@/domain/tasks'
import type { ArtifactFile, Task } from '@/types/models'

const props = defineProps<{
  selected: boolean
  task?: Task | null
  artifacts?: ArtifactFile[]
}>()

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
const isRunning = computed(() => ['pending', 'running'].includes(taskStatus.value))
const isFailure = computed(() => ['failure', 'canceled'].includes(taskStatus.value))
const progress = computed(() => Math.max(0, Math.min(100, Number(props.task?.progress ?? 0))))
const outputFiles = computed(() => props.task?.output_files ?? [])
const hasOutputs = computed(() => outputFiles.value.length > 0 || (props.task?.artifacts?.length ?? 0) > 0)
const visibleOutputFiles = computed(() => outputFiles.value.slice(0, 3))
const hiddenOutputCount = computed(() => Math.max(0, outputFiles.value.length - visibleOutputFiles.value.length))
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
.inline-preview-output-list {
  display: grid;
  align-content: center;
  gap: @spacing-xs;
  padding: @spacing-sm;
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
  border-color: rgba(59, 130, 246, 0.28);
  background: rgba(9, 9, 11, 0.82);
  color: @text-color-light-primary;
  font-size: @font-size-xs;
  font-weight: 800;
  backdrop-filter: blur(8px);
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.28);
  pointer-events: auto;
}

.inline-preview-expand-button:hover,
.inline-preview-expand-button:focus-visible {
  border-color: @accent-color;
  color: @accent-color-hover;
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
