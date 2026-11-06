<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import TaskContextBar from '@/components/tasks/TaskContextBar.vue'
import FunnelChart from './FunnelChart.vue'
import { countPasses, funnelFromRankedRows } from './funnel'
import type { FunnelStageKey } from './funnel'
import { loadMoleculeTable } from '@/views/predict/molecule-table'
import { downloadCsv } from '@/views/predict/csv-export'
import {
  SCREENING_RANKED_COLUMNS,
  SCREENING_RANKED_COLUMN_I18N
} from '@/types/screening'
import type { CsvPreviewRow } from '@/domain/tasks/csv-result'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const taskId = computed(() => String(route.params.id ?? ''))
const loading = ref(true)
const errorMessage = ref('')
const rows = ref<CsvPreviewRow[]>([])

const NUMERIC_KEYS = ['mol_weight', 'logp', 'qed', 'docking_score', 'rank']

function columnTitle(key: string): string {
  const suffix = SCREENING_RANKED_COLUMN_I18N[key]
  return suffix ? t(`screening.result.${suffix}`) : key
}

function isPass(raw: string | undefined): boolean {
  const value = (raw ?? '').trim().toLowerCase()
  return value === 'true' || value === '1' || value === 'yes'
}

function isStageColumn(key: string): boolean {
  return key === 'stage_pharmacophore' || key === 'stage_docking' || key === 'stage_rescore'
}

const tableColumns = computed(() =>
  SCREENING_RANKED_COLUMNS.map(key => {
    const numeric = NUMERIC_KEYS.includes(key)
    return {
      title: columnTitle(key),
      dataIndex: key,
      key,
      width: key === 'smiles' ? 220 : 120,
      align: numeric ? 'right' : 'left',
      sorter: numeric
        ? (left: CsvPreviewRow, right: CsvPreviewRow): number =>
            Number(left[key] ?? 0) - Number(right[key] ?? 0)
        : undefined
    }
  })
)

const exportColumns = computed(() =>
  SCREENING_RANKED_COLUMNS.map(key => ({ key, title: columnTitle(key) }))
)

const funnelStages = computed(() => funnelFromRankedRows(rows.value))
const keptCount = computed(() => countPasses(rows.value))

const stageLabels = computed<Record<FunnelStageKey, string>>(() => ({
  input: t('screening.result.stageInput'),
  pharmacophore: t('screening.result.stagePharmacophore'),
  docking: t('screening.result.stageDocking'),
  rescore: t('screening.result.stageRescore')
}))

const stageRows = computed(() =>
  funnelStages.value.map((stage, index) => {
    const previous =
      index === 0 ? stage.remaining : (funnelStages.value[index - 1]?.remaining ?? stage.remaining)
    return {
      key: stage.key,
      label: stageLabels.value[stage.key],
      remaining: stage.remaining,
      eliminated: index === 0 ? 0 : previous - stage.remaining
    }
  })
)

function openPose(record: CsvPreviewRow): void {
  const rankValue = Number(record.rank)
  const rank = Number.isFinite(rankValue) ? rankValue : 0
  void router.push({ path: `/docking-results/pose-${rank}`, query: { task_id: taskId.value } })
}

function customRow(record: CsvPreviewRow) {
  return {
    style: { cursor: 'pointer' },
    onClick: () => openPose(record)
  }
}

function handleExport(): void {
  downloadCsv(`screening-${taskId.value}.csv`, exportColumns.value, rows.value)
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await loadMoleculeTable(taskId.value)
    rows.value = data.rows
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t('screening.result.loadFailed')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <main class="screen-result" data-testid="screen-result-page">
    <AppPageHeader :title="t('screening.result.title')" :subtitle="t('screening.result.subtitle')">
      <template #actions>
        <a-button
          type="primary"
          :disabled="!rows.length"
          data-testid="screen-result-export"
          @click="handleExport"
        >
          {{ t('screening.result.exportCsv') }}
        </a-button>
      </template>
    </AppPageHeader>

    <TaskContextBar :task-id="taskId" active="result" :result-path="route.fullPath" />

    <a-alert
      v-if="errorMessage"
      type="error"
      show-icon
      data-testid="screen-result-error"
      :message="errorMessage"
    />

    <div v-if="loading" data-testid="screen-result-loading">
      <a-spin /> {{ t('screening.result.loading') }}
    </div>

    <a-empty
      v-else-if="!errorMessage && !rows.length"
      data-testid="screen-result-empty"
      :description="t('screening.result.empty')"
    />

    <template v-else-if="!errorMessage">
      <a-row :gutter="16">
        <a-col :xs="24" :lg="12">
          <a-card :title="t('screening.result.funnel')" data-testid="screen-result-funnel">
            <FunnelChart :stages="funnelStages" :labels="stageLabels" />
          </a-card>
        </a-col>
        <a-col :xs="24" :lg="12">
          <a-card :title="t('screening.result.stats')">
            <a-statistic :title="t('screening.result.count')" :value="rows.length" />
            <a-statistic :title="t('screening.result.kept')" :value="keptCount" />
            <a-table
              :columns="[
                { title: '', dataIndex: 'label', key: 'label' },
                { title: t('screening.result.passed'), dataIndex: 'remaining', key: 'remaining', align: 'right' },
                { title: t('screening.result.eliminated'), dataIndex: 'eliminated', key: 'eliminated', align: 'right' }
              ]"
              :data-source="stageRows"
              :pagination="false"
              row-key="key"
              size="small"
            />
          </a-card>
        </a-col>
      </a-row>

      <a-card :title="t('screening.result.table')">
        <a-table
          :columns="tableColumns"
          :data-source="rows"
          :pagination="{ pageSize: 20, showSizeChanger: true }"
          :scroll="{ x: 'max-content' }"
          :row-key="(_record: Record<string, string>, index: number) => index"
          :custom-row="customRow"
          size="small"
          data-testid="screen-result-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'passes'">
              <a-tag :color="isPass(record.passes) ? 'green' : 'default'">
                {{ isPass(record.passes) ? t('screening.result.yes') : t('screening.result.no') }}
              </a-tag>
            </template>
            <template v-else-if="isStageColumn(column.key)">
              <a-tag :color="isPass(record[column.key]) ? 'green' : 'default'">
                {{ isPass(record[column.key]) ? t('screening.result.yes') : t('screening.result.no') }}
              </a-tag>
            </template>
          </template>
        </a-table>
      </a-card>
    </template>
  </main>
</template>

<style scoped lang="less">
.screen-result {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
}
</style>
