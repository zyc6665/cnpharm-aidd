<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import TaskContextBar from '@/components/tasks/TaskContextBar.vue'
import HistogramChart from './HistogramChart.vue'
import MoleculePredictDetail from './MoleculePredictDetail.vue'
import { loadMoleculeTable } from './molecule-table'
import { filterPredictRows } from './predict-filter'
import { isNumericColumn, toNumericValues } from './histogram'
import { downloadCsv } from './csv-export'
import { PREDICT_COLUMN_I18N } from '@/types/predict'
import { resolveModelFamily } from '@/domain/design/modelFamilies'
import type { CsvPreviewColumn, CsvPreviewRow } from '@/domain/tasks/csv-result'

const route = useRoute()
const { t } = useI18n()

const taskId = computed(() => String(route.params.id ?? ''))
const loading = ref(true)
const errorMessage = ref('')
const columns = ref<CsvPreviewColumn[]>([])
const rows = ref<CsvPreviewRow[]>([])
const modelFamily = ref<string | null>(null)
const toolName = ref('')

const searchText = ref('')
const filterColumn = ref<string>('')
const filterMin = ref<number | null>(null)
const filterMax = ref<number | null>(null)
const affinityMin = ref<number | null>(null)

const detailOpen = ref(false)
const detailRow = ref<CsvPreviewRow | null>(null)

function openDetail(record: CsvPreviewRow): void {
  detailRow.value = record
  detailOpen.value = true
}

function columnTitle(key: string, fallback: string): string {
  const suffix = PREDICT_COLUMN_I18N[key]
  return suffix ? t(`predict.result.${suffix}`) : fallback
}

const numericColumns = computed(() =>
  columns.value.filter(column => isNumericColumn(rows.value, column.key))
)

const hasSmilesColumn = computed(() =>
  columns.value.some(column => column.key.toLowerCase() === 'smiles' || column.originalKey?.toLowerCase() === 'smiles')
)

/** 身份、时间和量表字段不适合作为筛选条件。 */
const FILTER_EXCLUDED_PATTERN = /(^|\.)(complex_id|molecule_id|smiles|duration_sec|scale)$/i

const filterColumnOptions = computed(() =>
  numericColumns.value
    .filter(column => !FILTER_EXCLUDED_PATTERN.test(column.key))
    .map(column => ({ label: columnTitle(column.key, column.title), value: column.key }))
)

const affinityColumnKey = computed(
  () => columns.value.find(column => /predicted_affinity/i.test(`${column.key} ${column.originalKey ?? ''}`))?.key ?? ''
)

const isAffinityResult = computed(() => modelFamily.value === 'affinity' || Boolean(affinityColumnKey.value))

const filterRangeInvalid = computed(
  () => filterMin.value !== null && filterMax.value !== null && filterMin.value > filterMax.value
)

const matrixColumns = computed(() => {
  const mapped = columns.value.map((column, index) => {
    const numeric = isNumericColumn(rows.value, column.key)
    return {
      title: columnTitle(column.key, column.title),
      dataIndex: column.key,
      key: column.key,
      width: column.key === 'smiles' ? 240 : 130,
      fixed: index === 0 ? 'left' : undefined,
      align: numeric ? 'right' : 'left',
      sorter: numeric
        ? (left: CsvPreviewRow, right: CsvPreviewRow): number =>
            Number(left[column.key] ?? 0) - Number(right[column.key] ?? 0)
        : undefined
    }
  })
  return [
    ...mapped,
    {
      title: t('predict.result.detail'),
      dataIndex: '__detail',
      key: '__detail',
      width: 96,
      fixed: 'right' as const,
      align: 'center' as const
    }
  ]
})

const filteredRows = computed(() =>
  filterPredictRows(rows.value, {
    searchText: searchText.value,
    hasSmilesColumn: hasSmilesColumn.value,
    isAffinityResult: isAffinityResult.value,
    affinityColumnKey: affinityColumnKey.value,
    affinityMin: affinityMin.value,
    column: filterColumn.value,
    min: filterMin.value,
    max: filterMax.value
  })
)

const exportColumns = computed(() =>
  matrixColumns.value.map(column => ({ key: column.key, title: String(column.title) }))
)

function resetFilter(): void {
  searchText.value = ''
  filterColumn.value = ''
  filterMin.value = null
  filterMax.value = null
  affinityMin.value = null
}

function handleFilterColumnChange(value: string | undefined): void {
  if (!value) {
    filterMin.value = null
    filterMax.value = null
  }
}

function handleExport(): void {
  downloadCsv(`predictions-${taskId.value}.csv`, exportColumns.value, filteredRows.value)
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await loadMoleculeTable(taskId.value)
    columns.value = data.columns
    rows.value = data.rows
    toolName.value = data.detail.tool_name ?? ''
    modelFamily.value = data.detail.model_family
      ?? resolveModelFamily({ slug: data.detail.tool_slug ?? undefined })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t('predict.result.loadFailed')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <main class="predict-result" data-testid="predict-result-page">
    <AppPageHeader :title="t('predict.result.title')" :subtitle="t('predict.result.subtitle')">
      <template #actions>
        <a-button
          type="primary"
          :disabled="!filteredRows.length"
          data-testid="predict-result-export"
          @click="handleExport"
        >
          {{ t('predict.result.exportCsv') }}
        </a-button>
      </template>
    </AppPageHeader>

    <TaskContextBar :task-id="taskId" active="result" :result-path="route.fullPath" />

    <a-alert
      v-if="errorMessage"
      type="error"
      show-icon
      data-testid="predict-result-error"
      :message="errorMessage"
    />

    <div v-if="loading" data-testid="predict-result-loading">
      <a-spin /> {{ t('predict.result.loading') }}
    </div>

    <a-empty
      v-else-if="!errorMessage && !rows.length"
      data-testid="predict-result-empty"
      :description="t('predict.result.empty')"
    />

    <template v-else-if="!errorMessage">
      <a-card class="predict-result__filters" :title="t('predict.result.filterTitle')">
        <a-space wrap>
          <a-input
            v-if="hasSmilesColumn"
            v-model:value="searchText"
            style="width: 220px"
            allow-clear
            :placeholder="t('predict.result.search')"
          />
          <template v-if="isAffinityResult">
            <a-input-number
              v-model:value="affinityMin"
              style="width: 260px"
              :addon-before="t('predict.result.affinityFilterLabel')"
              :placeholder="t('predict.result.filterMin')"
            />
          </template>
          <template v-else>
            <a-select
              v-model:value="filterColumn"
              style="width: 200px"
              allow-clear
              :placeholder="t('predict.result.filterColumn')"
              :options="filterColumnOptions"
              @change="handleFilterColumnChange"
            />
            <a-input-number
              v-model:value="filterMin"
              style="width: 150px"
              :disabled="!filterColumn"
              :placeholder="t('predict.result.filterMin')"
            />
            <a-input-number
              v-model:value="filterMax"
              style="width: 150px"
              :disabled="!filterColumn"
              :placeholder="t('predict.result.filterMax')"
            />
          </template>
          <a-button data-testid="predict-result-reset" @click="resetFilter">
            {{ t('predict.result.resetFilter') }}
          </a-button>
          <span class="predict-result__count">
            {{ t('predict.result.filterCount', { shown: filteredRows.length, total: rows.length }) }}
          </span>
          <span v-if="filterRangeInvalid" class="predict-result__filter-warning">
            {{ t('predict.result.filterRangeInvalid') }}
          </span>
        </a-space>
      </a-card>

      <a-card :title="t('predict.result.matrix')">
        <p class="predict-result__hint">{{ t('predict.result.detailHint') }}</p>
        <a-table
          :columns="matrixColumns"
          :data-source="filteredRows"
          :pagination="{ pageSize: 20, showSizeChanger: true }"
          :scroll="{ x: 'max-content' }"
          :row-key="(record: CsvPreviewRow) => record.__rowKey"
          :custom-row="(record: CsvPreviewRow) => ({ onClick: () => openDetail(record), style: 'cursor: pointer;' })"
          size="small"
          data-testid="predict-result-matrix"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === '__detail'">
              <a-button type="link" size="small" @click.stop="openDetail(record as CsvPreviewRow)">
                {{ t('predict.result.detail') }}
              </a-button>
            </template>
          </template>
        </a-table>
      </a-card>

      <a-card :title="t('predict.result.histograms')">
        <a-empty v-if="!numericColumns.length" :description="t('predict.result.noHistogram')" />
        <div v-else class="predict-result__charts">
          <div v-for="column in numericColumns" :key="column.key" class="predict-result__chart-cell">
            <HistogramChart
              :values="toNumericValues(rows, column.key)"
              :title="columnTitle(column.key, column.title)"
            />
          </div>
        </div>
      </a-card>

      <MoleculePredictDetail
        v-model:open="detailOpen"
        :row="detailRow"
        :rows="rows"
        :columns="columns"
        :task-id="taskId"
        :family="modelFamily"
        :tool-name="toolName"
        @select-candidate="detailRow = $event"
      />
    </template>
  </main>
</template>

<style scoped lang="less">
.predict-result {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
}

.predict-result__filters {
  margin-bottom: 0;
}

.predict-result__hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--ant-color-text-secondary, var(--theme-text-secondary));
}

.predict-result__count {
  color: var(--ant-color-text-secondary, var(--theme-text-secondary));
}

.predict-result__filter-warning {
  color: var(--ant-color-error, #e5484d);
  font-size: 12px;
}

.predict-result__charts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.predict-result__chart-cell {
  border: 1px solid var(--ant-color-border, var(--theme-border));
  border-radius: 8px;
  padding: 8px;
}
</style>
