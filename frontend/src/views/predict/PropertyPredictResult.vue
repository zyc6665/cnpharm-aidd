<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { DownOutlined, UpOutlined } from '@ant-design/icons-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import TaskContextBar from '@/components/tasks/TaskContextBar.vue'
import MoleculePredictDetail from './MoleculePredictDetail.vue'
import MetricDistributionChart from './MetricDistributionChart.vue'
import { loadMoleculeTable } from './molecule-table'
import { filterPredictRows } from './predict-filter'
import { isNumericColumn } from './histogram'
import { downloadCsv } from './csv-export'
import { PREDICT_COLUMN_I18N } from '@/types/predict'
import { resolveModelFamily } from '@/domain/design/modelFamilies'
import { resolvePredictDetailProfile } from './predictDetailProfiles'
import { buildPredictDistributionGroups } from './predict-distribution'
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

function hasNumericValue(key: string): boolean {
  return rows.value.some(row => {
    const raw = String(row[key] ?? '').trim()
    return raw !== '' && Number.isFinite(Number(raw))
  })
}

/** 分布只要求该指标至少有一个数值，不因个别缺失值而整列被排除。 */
const distributionColumns = computed(() =>
  columns.value.filter(column => !FILTER_EXCLUDED_PATTERN.test(column.key) && hasNumericValue(column.key))
)

interface DistributionOption {
  label: string
  value: string
}

interface DistributionGroup {
  label: string
  options: DistributionOption[]
}

/** 按模型能力族的指标分组（如吸收/分布/代谢/毒性）给分布指标下拉分组。 */
const distributionGroups = computed<DistributionGroup[]>(() => {
  const profile = resolvePredictDetailProfile(modelFamily.value)
  return buildPredictDistributionGroups(profile, distributionColumns.value).map(group => ({
    label: t(group.titleKey),
    options: group.columns.map(column => ({
      label: columnTitle(column.key, column.title),
      value: column.key
    }))
  }))
})

const distributionKey = ref('')
const distributionOpen = ref(false)

const distributionOptions = computed(() => distributionGroups.value)

const activeDistributionKey = computed(
  () => distributionKey.value || affinityColumnKey.value || distributionColumns.value[0]?.key || ''
)

const distributionColumn = computed(
  () => distributionColumns.value.find(column => column.key === activeDistributionKey.value) ?? null
)

const distributionPoints = computed(() => {
  const key = activeDistributionKey.value
  if (!key) {
    return []
  }
  return filteredRows.value
    .map((row, index) => ({
      label: String(row.molecule_id ?? row.complex_id ?? row.smiles ?? `#${index + 1}`),
      value: Number(String(row[key] ?? '').trim())
    }))
    .filter(point => Number.isFinite(point.value))
})

const distributionValues = computed(() => distributionPoints.value.map(point => point.value))

const distributionStats = computed(() => {
  const values = [...distributionValues.value].sort((left, right) => left - right)
  if (!values.length) {
    return null
  }
  const middle = Math.floor(values.length / 2)
  const median = values.length % 2
    ? values[middle]!
    : ((values[middle - 1] ?? 0) + (values[middle] ?? 0)) / 2
  return {
    count: values.length,
    min: values[0]!,
    median,
    max: values[values.length - 1]!
  }
})

watch(
  [distributionColumns, affinityColumnKey],
  ([columns, affinityKey]) => {
    if (distributionKey.value && columns.some(column => column.key === distributionKey.value)) {
      return
    }
    distributionKey.value = affinityKey || columns[0]?.key || ''
  },
  { immediate: true }
)

function formatStat(value: number): string {
  return Number(value.toFixed(3)).toString()
}

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

      <a-card class="predict-result__distribution">
        <template #title>
          <div class="predict-result__distribution-title">
            <span>{{ t('predict.result.histograms') }}</span>
            <span class="predict-result__distribution-hint">{{ t('predict.result.distributionHint') }}</span>
          </div>
        </template>
        <template #extra>
          <a-button type="link" size="small" data-testid="predict-distribution-toggle" @click="distributionOpen = !distributionOpen">
            {{ distributionOpen ? t('predict.result.distributionCollapse') : t('predict.result.distributionExpand') }}
            <UpOutlined v-if="distributionOpen" />
            <DownOutlined v-else />
          </a-button>
        </template>
        <div v-if="distributionOpen">
          <a-empty v-if="!distributionColumns.length" :description="t('predict.result.noHistogram')" />
          <template v-else>
            <div class="predict-result__distribution-toolbar">
              <span class="predict-result__distribution-label">{{ t('predict.result.distributionMetric') }}</span>
              <a-select
                v-model:value="distributionKey"
                style="width: 260px"
                :options="distributionOptions"
                data-testid="predict-distribution-metric"
              />
            </div>
            <div v-if="distributionStats" class="predict-result__distribution-stats">
              <div><span>{{ t('predict.result.distributionCount') }}</span><strong>{{ distributionStats.count }}</strong></div>
              <div><span>{{ t('predict.result.distributionMin') }}</span><strong>{{ formatStat(distributionStats.min) }}</strong></div>
              <div><span>{{ t('predict.result.distributionMedian') }}</span><strong>{{ formatStat(distributionStats.median) }}</strong></div>
              <div><span>{{ t('predict.result.distributionMax') }}</span><strong>{{ formatStat(distributionStats.max) }}</strong></div>
            </div>
            <MetricDistributionChart
              v-if="distributionColumn"
              :points="distributionPoints"
              :height="320"
              :bins="12"
              :median-label="t('predict.result.distributionMedian')"
            />
          </template>
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

.predict-result__distribution-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.predict-result__distribution-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--ant-color-text-secondary, var(--theme-text-secondary));
}

.predict-result__distribution-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.predict-result__distribution-label {
  font-size: 13px;
  color: var(--ant-color-text-secondary, var(--theme-text-secondary));
}

.predict-result__distribution-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.predict-result__distribution-stats > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--ant-color-border, var(--theme-border));
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary, rgba(0, 0, 0, 0.02));
}

.predict-result__distribution-stats span {
  font-size: 12px;
  color: var(--ant-color-text-secondary, var(--theme-text-secondary));
}

.predict-result__distribution-stats strong {
  font-size: 18px;
  font-variant-numeric: tabular-nums;
  color: var(--ant-color-text, inherit);
}
</style>
