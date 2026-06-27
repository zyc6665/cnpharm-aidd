<template>
  <div class="csv-result-viewer">
    <div class="csv-result-viewer__header">
      <div>
        <h5>{{ fileLabel }}</h5>
        <p>{{ summaryText }}</p>
      </div>
      <a-tag color="cyan">{{ t('tasks.csvPreview') }}</a-tag>
    </div>

    <a-spin :spinning="loading">
      <a-alert
        v-if="error"
        type="error"
        show-icon
        :message="t('tasks.csvLoadFailed')"
        :description="error"
      />

      <a-alert
        v-else-if="!preview.rows.length"
        type="info"
        show-icon
        :message="t('tasks.csvEmpty')"
        :description="t('tasks.csvEmptyDesc')"
      />

      <a-table
        v-else
        class="csv-result-viewer__table"
        :columns="tableColumns"
        :data-source="preview.rows"
        :pagination="false"
        :scroll="{ x: 'max-content', y: 560 }"
        row-key="__rowKey"
        size="small"
      >
        <template #bodyCell="{ column, record, text }">
          <Smiles2DCell
            v-if="column.key === structureColumnKey && preview.smilesColumnKey"
            :smiles="String(record[preview.smilesColumnKey] || '')"
          />
          <span v-else class="csv-result-viewer__cell">{{ formatCellValue(text) }}</span>
        </template>
      </a-table>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Task } from '@/types/models'
import { fetchProtectedFileText } from '@/utils/protected-file-access'

import Smiles2DCell from './Smiles2DCell.vue'
import { parseCsvPreview, type CsvPreview } from './csv-result'

const props = defineProps<{
  file: NonNullable<Task['output_files']>[number]
}>()

const { t } = useI18n()

const structureColumnKey = '__structure'
const loading = ref(false)
const error = ref('')
const preview = ref<CsvPreview>({
  columns: [],
  rows: [],
  smilesColumnKey: null
})

const fileLabel = computed(() => props.file.original_name || props.file.filename || t('tasks.csvPreview'))
const summaryText = computed(() =>
  t('tasks.csvSummary', {
    rows: preview.value.rows.length,
    columns: preview.value.columns.length
  })
)

const tableColumns = computed(() => {
  const columns: Array<Record<string, unknown>> = preview.value.columns.map(column => ({
    title: column.title,
    dataIndex: column.key,
    key: column.key,
    ellipsis: true
  }))

  if (preview.value.smilesColumnKey) {
    columns.unshift({
      title: t('tasks.csvStructure'),
      dataIndex: structureColumnKey,
      key: structureColumnKey,
      width: 172,
      fixed: 'left'
    })
  }

  return columns
})

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '-'
  }

  return String(value)
}

async function loadCsvPreview() {
  if (!props.file.url) {
    error.value = t('tasks.csvFileMissing')
    preview.value = {
      columns: [],
      rows: [],
      smilesColumnKey: null
    }
    return
  }

  loading.value = true
  error.value = ''

  try {
    const text = await fetchProtectedFileText(props.file.url)
    preview.value = parseCsvPreview(text)
  } catch (cause) {
    preview.value = {
      columns: [],
      rows: [],
      smilesColumnKey: null
    }
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.file.url,
  () => {
    void loadCsvPreview()
  },
  { immediate: true }
)
</script>

<style scoped>
.csv-result-viewer {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px;
  border-radius: 20px;
  background:
    radial-gradient(circle at top right, rgba(34, 197, 94, 0.08), transparent 28%),
    linear-gradient(180deg, @bg-elevated, @bg-hover);
  border: 1px solid #e2e8f0;
}

.csv-result-viewer__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.csv-result-viewer__header h5 {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
  color: #0f172a;
}

.csv-result-viewer__header p {
  margin: 0;
  color: #64748b;
  line-height: 1.6;
}

.csv-result-viewer__table :deep(.ant-table-container) {
  border-radius: 16px;
  overflow: hidden;
}

.csv-result-viewer__table :deep(.ant-table-thead > tr > th) {
  background: #eff6ff;
  color: #0f172a;
  font-weight: 600;
}

.csv-result-viewer__table :deep(.ant-table-tbody > tr > td) {
  vertical-align: top;
}

.csv-result-viewer__table :deep(.ant-table-body) {
  scrollbar-gutter: stable;
}

.csv-result-viewer__cell {
  display: inline-block;
  min-width: 120px;
  max-width: 420px;
  color: #334155;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 768px) {
  .csv-result-viewer {
    padding: 14px;
  }

  .csv-result-viewer__header {
    flex-direction: column;
  }
}
</style>
