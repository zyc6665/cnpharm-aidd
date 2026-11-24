<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { DownOutlined, UpOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { addCandidateSetItems, createCandidate, createCandidateSet } from '@/api/compounds'
import { getTaskDetail } from '@/api/tasks'
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
import { isValidHandoffSmiles, uploadMoleculeHandoff } from '@/domain/molecules/result-handoff'
import type { CsvPreviewColumn, CsvPreviewRow } from '@/domain/tasks/csv-result'
import ResultDisclaimer from '@/components/common/ResultDisclaimer.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const taskId = computed(() => String(route.params.id ?? ''))
const loading = ref(true)
const errorMessage = ref('')
const columns = ref<CsvPreviewColumn[]>([])
const rows = ref<CsvPreviewRow[]>([])
const modelFamily = ref<string | null>(null)
const toolName = ref('')
const searchText = ref('')
const filterColumn = ref('')
const filterMin = ref<number | null>(null)
const filterMax = ref<number | null>(null)
const affinityMin = ref<number | null>(null)
const MAX_SAVE_CANDIDATES = 200
const SAVE_BATCH_SIZE = 20
const detailOpen = ref(false)
const detailRow = ref<CsvPreviewRow | null>(null)
const selectedKeys = ref<string[]>([])
const handoffBusy = ref(false)
const saveModalOpen = ref(false)
const saveSetName = ref('')
const savingCandidates = ref(false)
const createdCandidateIds = new Map<string, string>()
const taskProjectId = ref('')
const distributionKey = ref('')
const distributionOpen = ref(false)

function openDetail(record: CsvPreviewRow): void { detailRow.value = record; detailOpen.value = true }
function columnTitle(key: string, fallback: string): string {
  const suffix = PREDICT_COLUMN_I18N[key]
  return suffix ? t(`predict.result.${suffix}`) : fallback
}
const numericColumns = computed(() => columns.value.filter(column => isNumericColumn(rows.value, column.key)))
const hasSmilesColumn = computed(() => columns.value.some(column => column.key.toLowerCase() === 'smiles' || column.originalKey?.toLowerCase() === 'smiles'))
const FILTER_EXCLUDED_PATTERN = /(^|\.)(complex_id|molecule_id|smiles|duration_sec|scale)$/i
const filterColumnOptions = computed(() => numericColumns.value.filter(column => !FILTER_EXCLUDED_PATTERN.test(column.key)).map(column => ({ label: columnTitle(column.key, column.title), value: column.key })))
const affinityColumnKey = computed(() => columns.value.find(column => /predicted_affinity/i.test(`${column.key} ${column.originalKey ?? ''}`))?.key ?? '')
const isAffinityResult = computed(() => modelFamily.value === 'affinity' || Boolean(affinityColumnKey.value))
const filterRangeInvalid = computed(() => filterMin.value !== null && filterMax.value !== null && filterMin.value > filterMax.value)
function hasNumericValue(key: string): boolean {
  return rows.value.some(row => { const raw = String(row[key] ?? '').trim(); return raw !== '' && Number.isFinite(Number(raw)) })
}
const distributionColumns = computed(() => columns.value.filter(column => !FILTER_EXCLUDED_PATTERN.test(column.key) && hasNumericValue(column.key)))
const distributionGroups = computed(() => {
  const profile = resolvePredictDetailProfile(modelFamily.value)
  return buildPredictDistributionGroups(profile, distributionColumns.value).map(group => ({ key: group.titleKey, label: t(group.titleKey), options: group.columns.map(column => ({ label: columnTitle(column.key, column.title), value: column.key })) }))
})
const distributionOptions = computed(() => distributionGroups.value.map(group => ({ value: group.key, label: group.label, children: group.options.map(option => ({ value: option.value, label: option.label })) })))
const activeDistributionKey = computed(() => distributionKey.value || affinityColumnKey.value || distributionColumns.value[0]?.key || '')
const distributionCascadeValue = computed<Array<string | number>>(() => {
  const group = distributionGroups.value.find(item => item.options.some(option => option.value === activeDistributionKey.value))
  return group ? [group.key, activeDistributionKey.value] : []
})
function handleDistributionCascadeChange(value: Array<string | number> | undefined): void {
  const selected = value?.length ? String(value[value.length - 1]) : ''
  if (selected) distributionKey.value = selected
}
const distributionColumn = computed(() => distributionColumns.value.find(column => column.key === activeDistributionKey.value) ?? null)
const filteredRows = computed(() => filterPredictRows(rows.value, {
  searchText: searchText.value, hasSmilesColumn: hasSmilesColumn.value, isAffinityResult: isAffinityResult.value,
  affinityColumnKey: affinityColumnKey.value, affinityMin: affinityMin.value, column: filterColumn.value,
  min: filterMin.value, max: filterMax.value
}))
const distributionPoints = computed(() => {
  const key = activeDistributionKey.value
  if (!key) return []
  return filteredRows.value.map((row, index) => ({ label: String(row.molecule_id ?? row.complex_id ?? row.smiles ?? `#${index + 1}`), value: Number(String(row[key] ?? '').trim()) })).filter(point => Number.isFinite(point.value))
})
const distributionStats = computed(() => {
  const values = distributionPoints.value.map(point => point.value).sort((a, b) => a - b)
  if (!values.length) return null
  const middle = Math.floor(values.length / 2)
  const median = values.length % 2 ? values[middle]! : ((values[middle - 1] ?? 0) + (values[middle] ?? 0)) / 2
  return { count: values.length, min: values[0]!, median, max: values[values.length - 1]! }
})
watch([distributionColumns, affinityColumnKey], ([available, affinityKey]) => {
  if (distributionKey.value && available.some(column => column.key === distributionKey.value)) return
  distributionKey.value = affinityKey || available[0]?.key || ''
}, { immediate: true })
function formatStat(value: number): string { return Number(value.toFixed(3)).toString() }

const matrixColumns = computed(() => {
  const mapped = columns.value.map((column, index) => {
    const numeric = isNumericColumn(rows.value, column.key)
    return {
      title: columnTitle(column.key, column.title), dataIndex: column.key, key: column.key,
      width: column.key === 'smiles' ? 240 : 130, fixed: index === 0 ? 'left' : undefined,
      align: numeric ? 'right' : 'left',
      sorter: numeric ? (left: CsvPreviewRow, right: CsvPreviewRow): number => {
        const parse = (raw: string | undefined) => raw?.trim() ? Number(raw) : Number.NaN
        const a = parse(left[column.key]); const b = parse(right[column.key])
        return (Number.isFinite(a) ? a : Infinity) - (Number.isFinite(b) ? b : Infinity)
      } : undefined
    }
  })
  return [...mapped, { title: t('predict.result.detail'), dataIndex: '__detail', key: '__detail', width: 96, fixed: 'right' as const, align: 'center' as const }]
})
const exportColumns = computed(() => columns.value.map(column => ({ key: column.key, title: columnTitle(column.key, column.title) })))
const selectedRows = computed(() => rows.value.filter(row => selectedKeys.value.includes(row.__rowKey ?? '')))
const eligibleFilteredRows = computed(() => filteredRows.value.filter(row => isValidHandoffSmiles(row.smiles ?? '')))
const handoffScopeRows = computed(() => (selectedKeys.value.length
  ? selectedRows.value.filter(row => filteredRows.value.includes(row) && isValidHandoffSmiles(row.smiles ?? ''))
  : eligibleFilteredRows.value))
const handoffRows = computed(() => handoffScopeRows.value.slice(0, MAX_SAVE_CANDIDATES))
const saveSkippedCount = computed(() => Math.max(0, filteredRows.value.length - eligibleFilteredRows.value.length))
const rowSelection = computed(() => ({ selectedRowKeys: selectedKeys.value, preserveSelectedRowKeys: true, onChange: (keys: Array<string | number>) => { selectedKeys.value = keys.map(String) } }))
function resetFilter(): void { searchText.value = ''; filterColumn.value = ''; filterMin.value = null; filterMax.value = null; affinityMin.value = null }
function handleFilterColumnChange(value: string | undefined): void { if (!value) { filterMin.value = null; filterMax.value = null } }
function handleExport(): void { downloadCsv(`predictions-${taskId.value}.csv`, exportColumns.value, filteredRows.value) }
async function projectIdForTask(): Promise<string> {
  if (taskProjectId.value) return taskProjectId.value
  const queryProject = typeof route.query.project_id === 'string' ? route.query.project_id : ''
  if (queryProject) return taskProjectId.value = queryProject
  const response = await getTaskDetail(taskId.value, { silent: true })
  return taskProjectId.value = response.data.project_id ?? ''
}
function openSaveModal(): void {
  saveSetName.value = t('predict.result.defaultSetName', { id: taskId.value.slice(0, 8) })
  saveModalOpen.value = true
}
async function handleSaveCandidates(): Promise<void> {
  if (savingCandidates.value || !saveSetName.value.trim() || !handoffRows.value.length) return
  const activeTaskId = taskId.value
  const snapshot = [...handoffRows.value]
  const name = saveSetName.value.trim()
  const projectId = await projectIdForTask().catch(() => '')
  if (!projectId) { message.error(t('predict.result.noProject')); return }
  savingCandidates.value = true
  try {
    const pending = snapshot.filter(row => !createdCandidateIds.has(row.__rowKey ?? ''))
    for (let offset = 0; offset < pending.length; offset += SAVE_BATCH_SIZE) {
      const batch = pending.slice(offset, offset + SAVE_BATCH_SIZE)
      const created = await Promise.all(batch.map(async row => {
        const result = await createCandidate(projectId, {
          candidate_type: 'SMALL_MOLECULE', source: 'IMPORT', task_id: activeTaskId,
          smiles: (row.smiles ?? '').trim(), attrs: { ...row }
        })
        return { key: row.__rowKey ?? '', id: result.data.id }
      }))
      for (const item of created) { if (item.key) createdCandidateIds.set(item.key, item.id) }
    }
    const candidateIds = snapshot.map(row => createdCandidateIds.get(row.__rowKey ?? '')).filter((id): id is string => Boolean(id))
    const set = await createCandidateSet(projectId, { name, description: t('predict.result.setDescription', { id: activeTaskId }), source_task_id: activeTaskId })
    await addCandidateSetItems(set.data.id, { candidate_ids: candidateIds })
    if (taskId.value !== activeTaskId) return
    createdCandidateIds.clear()
    saveModalOpen.value = false
    message.success(t('predict.result.saved', { count: candidateIds.length }))
  } catch (error) {
    const partial = snapshot.filter(row => createdCandidateIds.has(row.__rowKey ?? '')).length
    if (partial > 0) message.warning(t('predict.result.savePartial', { created: partial, total: snapshot.length }))
    else message.error(error instanceof Error ? error.message : t('predict.result.saveFailed'))
  } finally {
    savingCandidates.value = false
  }
}
async function sendToScreening(): Promise<void> {
  if (handoffBusy.value || !handoffRows.value.length) return
  handoffBusy.value = true
  const activeTaskId = taskId.value
  const snapshot = [...handoffRows.value]
  try {
    const projectId = await projectIdForTask()
    if (!projectId) { message.error(t('predict.result.noProject')); return }
    const file = await uploadMoleculeHandoff(snapshot.map(row => ({ smiles: row.smiles ?? '', moleculeId: row.molecule_id || undefined })), `prediction-${activeTaskId}-screening.csv`)
    if (taskId.value !== activeTaskId) return
    await router.push({ name: 'ScreenConfig', query: { project_id: projectId, ...file } })
    message.success(t('predict.result.handoffSent', { count: snapshot.length }))
  } catch (error) { message.error(error instanceof Error ? error.message : t('predict.result.handoffFailed')) }
  finally { handoffBusy.value = false }
}
let requestSequence = 0
async function load(): Promise<void> {
  const id = taskId.value
  if (!id) return
  const sequence = ++requestSequence
  loading.value = true; errorMessage.value = ''; rows.value = []; columns.value = []; selectedKeys.value = []; taskProjectId.value = ''; createdCandidateIds.clear()
  try {
    const data = await loadMoleculeTable(id)
    if (sequence !== requestSequence) return
    columns.value = data.columns; rows.value = data.rows; toolName.value = data.detail.tool_name ?? ''
    taskProjectId.value = data.detail.project_id ?? ''
    modelFamily.value = data.detail.model_family ?? resolveModelFamily({ slug: data.detail.tool_slug ?? undefined })
  } catch (error) {
    if (sequence === requestSequence) errorMessage.value = error instanceof Error ? error.message : t('predict.result.loadFailed')
  } finally { if (sequence === requestSequence) loading.value = false }
}
watch(taskId, () => { void load() }, { immediate: true })
</script>

<template>
  <main class="predict-result" data-testid="predict-result-page">
    <AppPageHeader :title="t('predict.result.title')" :subtitle="t('predict.result.subtitle')"><template #actions><a-space>
      <a-button :disabled="!handoffRows.length" data-testid="predict-save-candidates" @click="openSaveModal">{{ t('predict.result.saveCandidates', { count: handoffRows.length }) }}</a-button>
      <a-button :disabled="!handoffRows.length" :loading="handoffBusy" data-testid="predict-result-send-screening" @click="sendToScreening">{{ t('predict.result.sendScreening', { count: handoffRows.length }) }}</a-button>
      <a-button type="primary" :disabled="!filteredRows.length" data-testid="predict-result-export" @click="handleExport">{{ t('predict.result.exportCsv') }}</a-button>
    </a-space></template></AppPageHeader>
    <TaskContextBar :task-id="taskId" active="result" :result-path="route.fullPath" />
    <a-alert v-if="errorMessage" type="error" show-icon data-testid="predict-result-error" :message="errorMessage" />
    <div v-if="loading" data-testid="predict-result-loading"><a-spin /> {{ t('predict.result.loading') }}</div>
    <a-empty v-else-if="!errorMessage && !rows.length" data-testid="predict-result-empty" :description="t('predict.result.empty')" />
    <template v-else-if="!errorMessage">
      <a-card class="predict-result__filters" :title="t('predict.result.filterTitle')"><a-space wrap>
        <a-input v-if="hasSmilesColumn" v-model:value="searchText" style="width: 220px" allow-clear :placeholder="t('predict.result.search')" />
        <template v-if="isAffinityResult"><a-input-number v-model:value="affinityMin" style="width: 260px" :addon-before="t('predict.result.affinityFilterLabel')" :placeholder="t('predict.result.filterMin')" /></template>
        <template v-else><a-select v-model:value="filterColumn" style="width: 200px" allow-clear :placeholder="t('predict.result.filterColumn')" :options="filterColumnOptions" @change="handleFilterColumnChange" /><a-input-number v-model:value="filterMin" style="width: 150px" :disabled="!filterColumn" :placeholder="t('predict.result.filterMin')" /><a-input-number v-model:value="filterMax" style="width: 150px" :disabled="!filterColumn" :placeholder="t('predict.result.filterMax')" /></template>
        <a-button data-testid="predict-result-reset" @click="resetFilter">{{ t('predict.result.resetFilter') }}</a-button><span class="predict-result__count">{{ t('predict.result.filterCount', { shown: filteredRows.length, total: rows.length }) }}</span><span v-if="filterRangeInvalid" class="predict-result__filter-warning">{{ t('predict.result.filterRangeInvalid') }}</span>
      </a-space></a-card>
      <a-card :title="t('predict.result.matrix')"><p class="predict-result__hint">{{ t('predict.result.detailHint') }}</p>
        <a-table :columns="matrixColumns" :data-source="filteredRows" :row-selection="rowSelection" :pagination="{ pageSize: 20, showSizeChanger: true }" :scroll="{ x: 'max-content' }" :row-key="(record: CsvPreviewRow) => record.__rowKey" :custom-row="(record: CsvPreviewRow) => ({ onClick: () => openDetail(record), style: 'cursor: pointer;' })" size="small" data-testid="predict-result-matrix"><template #bodyCell="{ column, record }"><template v-if="column.key === '__detail'"><a-button type="link" size="small" @click.stop="openDetail(record as CsvPreviewRow)">{{ t('predict.result.detail') }}</a-button></template></template></a-table>
      </a-card>
      <a-card class="predict-result__distribution"><template #title><div class="predict-result__distribution-title"><span>{{ t('predict.result.histograms') }}</span><span class="predict-result__distribution-hint">{{ t('predict.result.distributionHint') }}</span></div></template><template #extra><a-button type="link" size="small" data-testid="predict-distribution-toggle" @click="distributionOpen = !distributionOpen">{{ distributionOpen ? t('predict.result.distributionCollapse') : t('predict.result.distributionExpand') }}<UpOutlined v-if="distributionOpen" /><DownOutlined v-else /></a-button></template>
        <div v-if="distributionOpen"><a-empty v-if="!distributionColumns.length" :description="t('predict.result.noHistogram')" /><template v-else><div class="predict-result__distribution-toolbar"><span class="predict-result__distribution-label">{{ t('predict.result.distributionMetric') }}</span><a-cascader :value="distributionCascadeValue" :options="distributionOptions" :placeholder="t('predict.result.distributionMetric')" expand-trigger="hover" :show-search="true" style="width: 320px" data-testid="predict-distribution-metric" @change="handleDistributionCascadeChange" /></div><div v-if="distributionStats" class="predict-result__distribution-stats"><div><span>{{ t('predict.result.distributionCount') }}</span><strong>{{ distributionStats.count }}</strong></div><div><span>{{ t('predict.result.distributionMin') }}</span><strong>{{ formatStat(distributionStats.min) }}</strong></div><div><span>{{ t('predict.result.distributionMedian') }}</span><strong>{{ formatStat(distributionStats.median) }}</strong></div><div><span>{{ t('predict.result.distributionMax') }}</span><strong>{{ formatStat(distributionStats.max) }}</strong></div></div><MetricDistributionChart v-if="distributionColumn" :points="distributionPoints" :height="320" :bins="12" :median-label="t('predict.result.distributionMedian')" /></template></div>
      </a-card>
      <MoleculePredictDetail v-model:open="detailOpen" :row="detailRow" :rows="rows" :columns="columns" :task-id="taskId" :family="modelFamily" :tool-name="toolName" @select-candidate="detailRow = $event" />
    </template>
    <a-modal v-model:open="saveModalOpen" :title="t('predict.result.saveCandidates', { count: handoffRows.length })" :confirm-loading="savingCandidates" :ok-text="t('predict.result.saveButton')" data-testid="predict-save-candidates-modal" @ok="handleSaveCandidates">
      <a-form layout="vertical">
        <a-form-item :label="t('predict.result.setName')" required>
          <a-input v-model:value="saveSetName" :placeholder="t('predict.result.setNamePlaceholder')" />
        </a-form-item>
        <p>{{ t('predict.result.saveScope', { count: handoffRows.length, total: handoffScopeRows.length, skipped: saveSkippedCount }) }}</p>
      </a-form>
    </a-modal>
  </main><ResultDisclaimer />
</template>

<style scoped lang="less">
.predict-result { display: flex; flex-direction: column; gap: 16px; padding: 24px; }
.predict-result__hint { margin: 0 0 10px; font-size: 12px; color: var(--ant-color-text-secondary, var(--theme-text-secondary)); }
.predict-result__count { color: var(--ant-color-text-secondary, var(--theme-text-secondary)); }
.predict-result__filter-warning { color: var(--ant-color-error, #e5484d); }
.predict-result__distribution-title { display: flex; align-items: baseline; gap: 12px; }
.predict-result__distribution-hint { color: var(--ant-color-text-secondary, var(--theme-text-secondary)); font-size: 12px; font-weight: normal; }
.predict-result__distribution-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.predict-result__distribution-label { color: var(--ant-color-text-secondary, var(--theme-text-secondary)); }
.predict-result__distribution-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.predict-result__distribution-stats > div { display: flex; flex-direction: column; gap: 4px; padding: 12px; border: 1px solid var(--ant-color-border, #e5e7eb); border-radius: 8px; background: var(--ant-color-fill-quaternary, rgba(0, 0, 0, 0.02)); }
.predict-result__distribution-stats span { color: var(--ant-color-text-secondary, var(--theme-text-secondary)); font-size: 12px; }
.predict-result__distribution-stats strong { font-size: 18px; font-variant-numeric: tabular-nums; color: var(--ant-color-text, inherit); }
@media (max-width: 640px) { .predict-result__distribution-title { align-items: flex-start; flex-direction: column; gap: 4px; } .predict-result__distribution-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } .predict-result__distribution-toolbar { align-items: flex-start; flex-direction: column; } }
</style>
