<template>
  <section class="inspector-section node-result-section">
    <div class="section-title">{{ t('workflow.inspector.taskResult') }}</div>

    <div v-if="node.type === 'tool'" class="result-actions">
      <a-button
        size="small"
        type="primary"
        :disabled="!canRerun"
        @click="$emit('configure-node', node.id)"
      >
        {{ t('workflow.inspector.configureNode') }}
      </a-button>
      <a-button size="small" :disabled="!task" @click="$emit('view-task-detail', node.id)">
        {{ t('workflow.inspector.viewTaskDetail') }}
      </a-button>
    </div>

    <div v-if="task" class="task-result-summary">
      <div class="result-summary-header">
        <div>
          <span class="result-summary-label">{{ t('workflow.inspector.resultSummary') }}</span>
          <strong>{{ statusText }}</strong>
        </div>
        <a-tag :color="statusColor">{{ statusText }}</a-tag>
      </div>

      <a-progress
        v-if="isRunning"
        :percent="task.progress ?? 0"
        :status="progressStatus"
        size="small"
      />

      <p v-if="task.progress_message && isRunning" class="result-message">
        {{ task.progress_message }}
      </p>
      <p v-if="task.error_message" class="result-message result-message-error">
        {{ task.error_message }}
      </p>

      <div class="result-summary-footer">
        <span>{{ t('workflow.inspector.resultStatus') }}</span>
        <strong>{{ statusText }}</strong>
        <span class="result-summary-separator">·</span>
        <span>{{ t('workflow.inspector.resultFileCount', { count: resultFiles.length }) }}</span>
      </div>
    </div>

    <a-empty v-else :description="t('workflow.inspector.noTaskResult')" />
  </section>

  <section class="inspector-section output-files-section">
    <div class="section-title output-files-title">
      <span>{{ t('workflow.inspector.outputFiles') }}</span>
      <span v-if="resultFiles.length" class="output-files-count">{{ resultFiles.length }}</span>
    </div>

    <div v-if="resultFiles.length" class="output-file-list">
      <div v-for="file in resultFiles" :key="file.key" class="output-file-item">
        <div class="output-file-main">
          <strong class="output-file-name">{{ file.filename }}</strong>
          <div class="output-file-meta">
            <span>{{ file.type }}</span>
            <span v-if="file.size !== undefined">{{ formatTaskFileSize(file.size) }}</span>
          </div>
        </div>
        <a-button
          v-if="file.url"
          size="small"
          type="text"
          class="output-file-download"
          :aria-label="t('workflow.inspector.downloadResult')"
          @click="download(file)"
        >
          {{ t('workflow.inspector.downloadResult') }}
        </a-button>
      </div>
    </div>

    <a-empty v-else :description="t('workflow.inspector.noOutputFiles')" />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import type { ArtifactFile } from '@/types/models'
import type { WorkflowTaskRef } from '@/workflow/artifact-types'
import type { WorkflowCanvasNode } from '@/workflow/canvas-types'
import {
  formatTaskFileSize,
  getTaskProgressStatus,
  getTaskStatusColor,
  getTaskStatusTextKey,
  normalizeTaskStatus,
  runningStatuses
} from '@/domain/tasks'
import { triggerProtectedFileDownload } from '@/utils/protected-file-access'

type OutputFile = NonNullable<WorkflowTaskRef['output_files']>[number]

interface UserResultFile {
  key: string
  filename: string
  type: string
  size?: number
  url?: string
}

const props = defineProps<{
  node: WorkflowCanvasNode
  task?: WorkflowTaskRef | null
  artifacts?: ArtifactFile[]
  selectedToolSlug?: string | null
}>()

defineEmits<{
  (event: 'configure-node', nodeId: string): void
  (event: 'view-task-detail', nodeId: string): void
}>()

const { t } = useI18n()

const canRerun = computed(() => Boolean(
  props.selectedToolSlug || props.node.recommendedToolSlug || props.node.toolSlugs?.[0]
))

const normalizedStatus = computed(() => normalizeTaskStatus(props.task?.status))
const statusText = computed(() => t(getTaskStatusTextKey(normalizedStatus.value)))
const statusColor = computed(() => getTaskStatusColor(normalizedStatus.value))
const isRunning = computed(() => runningStatuses.includes(normalizedStatus.value))
const progressStatus = computed(() => getTaskProgressStatus(normalizedStatus.value))

function getFileType(filename: string, contentType?: string | null): string {
  const extension = filename.includes('.') ? filename.split('.').pop()?.toUpperCase() : ''
  return extension || contentType || t('workflow.inspector.resultFileTypeUnknown')
}

function toOutputFileResult(file: OutputFile, index: number): UserResultFile | null {
  const filename = file.filename || file.original_name || file.relative_path
  if (!filename) return null

  return {
    key: file.url || `output-${index}-${filename}`,
    filename,
    type: getFileType(filename, file.content_type),
    size: file.size,
    url: file.url
  }
}

const resultFiles = computed<UserResultFile[]>(() => {
  const outputFiles = (props.task?.output_files ?? [])
    .map((file, index) => toOutputFileResult(file, index))
    .filter((file): file is UserResultFile => Boolean(file))

  const artifactFiles = (props.artifacts ?? [])
    .filter(artifact => artifact.task_id === props.task?.id)
    .map(artifact => ({
      key: artifact.download_url || artifact.filename,
      filename: artifact.filename,
      type: getFileType(artifact.filename, artifact.content_type),
      size: artifact.size_bytes,
      url: artifact.download_url
    }))

  const seenUrls = new Set<string>()
  const seenFilenames = new Set<string>()
  return [...outputFiles, ...artifactFiles].filter(file => {
    const normalizedFilename = file.filename.toLowerCase()
    if ((file.url && seenUrls.has(file.url)) || seenFilenames.has(normalizedFilename)) {
      return false
    }

    if (file.url) seenUrls.add(file.url)
    seenFilenames.add(normalizedFilename)
    return true
  })
})

async function download(file: UserResultFile) {
  if (!file.url) return

  try {
    await triggerProtectedFileDownload({
      url: file.url,
      filename: file.filename,
      original_name: file.filename
    })
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('common.error'))
  }
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.node-result-section,
.output-files-section {
  display: flex;
  flex-direction: column;
  gap: @spacing-sm;
}

.result-actions {
  display: flex;
  flex-wrap: wrap;
  gap: @spacing-xs;
}

.task-result-summary {
  padding: @spacing-md;
  border: 1px solid @border-color-light;
  border-radius: @border-radius-md;
  background: linear-gradient(135deg, @bg-light-secondary, @bg-surface);
}

.result-summary-header,
.result-summary-footer,
.output-files-title,
.output-file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: @spacing-sm;
}

.result-summary-header > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.result-summary-label,
.result-summary-footer,
.output-file-meta {
  color: @text-color-light-secondary;
  font-size: @font-size-xs;
}

.result-summary-header strong {
  color: @text-color-light-primary;
  font-size: @font-size-md;
}

.result-message {
  margin: @spacing-sm 0 0;
  color: @text-color-light-secondary;
  font-size: @font-size-xs;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.result-message-error {
  color: @error-color;
}

.result-summary-footer {
  justify-content: flex-start;
  margin-top: @spacing-sm;
}

.result-summary-footer strong {
  color: @text-color-light-primary;
}

.result-summary-separator {
  color: @text-color-light-tertiary;
}

.output-files-title {
  width: 100%;
}

.output-files-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 10px;
  background: @bg-light-secondary;
  color: @text-color-light-secondary;
  font-size: @font-size-xs;
}

.output-file-list {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid @border-color-light;
  border-radius: @border-radius-md;
}

.output-file-item {
  align-items: flex-start;
  padding: @spacing-sm @spacing-md;
  background: @bg-surface;
}

.output-file-item + .output-file-item {
  border-top: 1px solid @border-color-light;
}

.output-file-main {
  min-width: 0;
}

.output-file-name {
  display: block;
  overflow: hidden;
  color: @text-color-light-primary;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.output-file-meta {
  display: flex;
  flex-wrap: wrap;
  gap: @spacing-sm;
  margin-top: 3px;
}

.output-file-download {
  flex: 0 0 auto;
  padding: 0;
  color: @primary-color;
}
</style>
