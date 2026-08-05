<template>
  <div v-if="hasContent" class="task-output-summary">
    <div v-if="outputDataEntries.length" class="output-data">
      <JsonResultRenderer :value="outputData" />
    </div>

    <div v-if="outputFiles.length" class="files-section">
      <div class="files-header">
        <h4>{{ t('tasks.outputFiles') }}</h4>
        <a-button
          v-if="canShowMolpPcCsvExport"
          size="small"
          :loading="exportingMolpPcCsv"
          @click="exportMolpPcCsv"
        >
          <DownloadOutlined />
          {{ t('tasks.exportMolpPcCsv') }}
        </a-button>
      </div>
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
  import { computed, ref } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import { DownloadOutlined, FileOutlined } from '@ant-design/icons-vue'
  import type { Task } from '@/types/models'
  import { fetchProtectedFileText, triggerProtectedFileDownload } from '@/utils/protected-file-access'
  import JsonResultRenderer from './JsonResultRenderer.vue'
  import {
    buildMolpPcCsv,
    canExportMolpPcCsv,
    formatTaskFileSize,
    getTaskOutputDataEntries,
    getTaskOutputFiles,
    hasTaskOutputSummaryContent,
    selectMolpPcCsvSourceFile
  } from '@/domain/tasks'

  type TaskOutputFile = NonNullable<Task['output_files']>[number]

  const props = withDefaults(defineProps<{
    task: Task
    showBatchDownload?: boolean
  }>(), {
    showBatchDownload: true
  })

  const { t } = useI18n()
  const exportingMolpPcCsv = ref(false)

  const outputDataEntries = computed<[string, unknown][]>(() => {
    return getTaskOutputDataEntries(props.task.output_data)
  })

  const outputData = computed(() => props.task.output_data)

  const outputFiles = computed<TaskOutputFile[]>(() => {
    return getTaskOutputFiles(props.task)
  })

  const canShowMolpPcCsvExport = computed(() => canExportMolpPcCsv(outputFiles.value))

  const hasContent = computed(() => {
    return hasTaskOutputSummaryContent(props.task.output_data, outputFiles.value)
  })

  const formatFileSize = formatTaskFileSize

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

  function triggerTextDownload(filename: string, content: string) {
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')

    try {
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
    } finally {
      anchor.remove()
      URL.revokeObjectURL(url)
    }
  }

  async function exportMolpPcCsv() {
    const sourceFile = selectMolpPcCsvSourceFile(outputFiles.value)
    if (!sourceFile?.url) {
      message.error(t('tasks.exportMolpPcCsvNoSource'))
      return
    }

    exportingMolpPcCsv.value = true
    try {
      const sourceCsv = await fetchProtectedFileText(sourceFile.url)
      const molpPcCsv = buildMolpPcCsv(sourceCsv)

      if (!molpPcCsv) {
        message.error(t('tasks.exportMolpPcCsvNoSmiles'))
        return
      }

      triggerTextDownload('molp_pc_smiles.csv', molpPcCsv)
      message.success(t('tasks.exportMolpPcCsvSuccess'))
    } catch (cause) {
      const errorMessage = cause instanceof Error ? cause.message : String(cause)
      message.error(errorMessage)
    } finally {
      exportingMolpPcCsv.value = false
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

  .files-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
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
    background: linear-gradient(180deg, @bg-elevated 0%, @accent-color-light 100%);
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
