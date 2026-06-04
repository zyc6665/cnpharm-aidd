<template>
  <div v-if="hasContent" class="task-output-summary">
    <div v-if="outputDataEntries.length" class="output-data">
      <a-descriptions :column="1" bordered size="small">
        <a-descriptions-item
          v-for="[key, value] in outputDataEntries"
          :key="key"
          :label="String(key)"
        >
          <template v-if="typeof value === 'object'">
            <pre class="json-display">{{ JSON.stringify(value, null, 2) }}</pre>
          </template>
          <template v-else>
            {{ value }}
          </template>
        </a-descriptions-item>
      </a-descriptions>
    </div>

    <div v-if="outputFiles.length" class="files-section">
      <h4>{{ t('tasks.outputFiles') }}</h4>
      <div class="file-list">
        <div
          v-for="file in outputFiles"
          :key="String(file.id ?? file.filename ?? file.original_name)"
          class="file-item downloadable"
        >
          <FileOutlined />
          <span class="file-name">{{ file.original_name || file.filename }}</span>
          <span class="file-size">{{ formatFileSize(file.size) }}</span>
          <a-button type="link" size="small" @click="downloadFile(file)">
            <DownloadOutlined />
            {{ t('common.download') }}
          </a-button>
        </div>
      </div>

      <a-button
        v-if="showBatchDownload && outputFiles.length > 1"
        type="primary"
        class="download-all-btn"
        @click="downloadAllFiles"
      >
        <DownloadOutlined />
        {{ t('tasks.downloadAll') }}
      </a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import { DownloadOutlined, FileOutlined } from '@ant-design/icons-vue'
  import type { Task } from '@/types/models'
  import { triggerProtectedFileDownload } from '@/utils/protected-file-access'

  interface TaskOutputFile {
    id?: string | number
    original_name?: string
    filename?: string
    size?: number
    content_type?: string
    url?: string
  }

  const props = withDefaults(defineProps<{
    task: Task
    showBatchDownload?: boolean
  }>(), {
    showBatchDownload: true
  })

  const { t } = useI18n()

  const outputDataEntries = computed<[string, unknown][]>(() => {
    const outputData = props.task.output_data

    if (!outputData || typeof outputData !== 'object' || Array.isArray(outputData)) {
      return []
    }

    return Object.entries(outputData as Record<string, unknown>)
  })

  const outputFiles = computed<TaskOutputFile[]>(() => {
    return props.task.output_files ?? []
  })

  const hasContent = computed(() => {
    return outputDataEntries.value.length > 0 || outputFiles.value.length > 0
  })

  function formatFileSize(bytes?: number) {
    if (!bytes || bytes === 0) {
      return '0 B'
    }

    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
  }

  async function downloadFile(file: TaskOutputFile) {
    try {
      await triggerProtectedFileDownload(file)
    } catch (cause) {
      const errorMessage = cause instanceof Error ? cause.message : String(cause)
      message.error(errorMessage)
    }
  }

  async function downloadAllFiles() {
    for (const file of outputFiles.value) {
      await downloadFile(file)
    }
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .task-output-summary {
    display: flex;
    flex-direction: column;
    gap: @spacing-lg;
  }

  .json-display {
    margin: 0;
    padding: @spacing-sm;
    border-radius: @border-radius-md;
    background: #f8fafc;
    color: @text-color-light-primary;
    overflow-x: auto;
  }

  .files-section {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;

    h4 {
      margin: 0;
      font-size: @font-size-md;
      font-weight: @font-weight-semibold;
      color: @text-color-light-primary;
    }
  }

  .file-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .file-item {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    padding: @spacing-sm @spacing-md;
    border: 1px solid rgba(220, 227, 240, 0.92);
    border-radius: @border-radius-md;
    background: linear-gradient(180deg, #fff 0%, #f8fbff 100%);
  }

  .file-name {
    flex: 1;
    min-width: 0;
    color: @text-color-light-primary;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .file-size {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    white-space: nowrap;
  }

  .download-all-btn {
    align-self: flex-start;
  }

  @media (max-width: @screen-sm) {
    .file-item {
      flex-wrap: wrap;
    }

    .file-name {
      white-space: normal;
    }
  }
</style>
