<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import TaskContextBar from '@/components/tasks/TaskContextBar.vue'
import FunnelChart from './FunnelChart.vue'
import { countPasses, funnelFromRankedRows, isTruthyFlag } from './funnel'
import type { FunnelStageKey } from './funnel'
import { loadMoleculeTable } from '@/views/predict/molecule-table'
import { downloadCsv } from '@/views/predict/csv-export'
import { getTaskDetail } from '@/api/tasks'
import { addCandidateSetItems, createCandidate, createCandidateSet } from '@/api/compounds'
import { uploadMoleculeHandoff, isValidHandoffSmiles } from '@/domain/molecules/result-handoff'
import { SCREENING_RANKED_COLUMNS, SCREENING_RANKED_COLUMN_I18N } from '@/types/screening'
import type { CsvPreviewRow } from '@/domain/tasks/csv-result'
import type { Task } from '@/types/models'
import ResultDisclaimer from '@/components/common/ResultDisclaimer.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const MAX_SAVE_CANDIDATES = 200
const taskId = computed(() => String(route.params.id ?? ''))
const loading = ref(true)
const errorMessage = ref('')
const rows = ref<CsvPreviewRow[]>([])
const selectedRowKeys = ref<string[]>([])
const saveModalOpen = ref(false)
const saveSetName = ref('')
const savingCandidates = ref(false)
const handoffBusy = ref(false)
const mdBusy = ref(false)
const taskProjectId = ref('')
const taskDetail = ref<Task | null>(null)

function rowStableKey(record: CsvPreviewRow): string { return record.__rowKey ?? '' }
const passedRows = computed(() => rows.value.filter(row => isTruthyFlag(row.passes) && isValidHandoffSmiles(row.smiles ?? '')))
const handoffRows = computed(() => {
  const eligible = selectedRowKeys.value.length
    ? passedRows.value.filter(row => selectedRowKeys.value.includes(rowStableKey(row)))
    : passedRows.value
  return eligible.slice(0, MAX_SAVE_CANDIDATES)
})
const saveScopeText = computed(() => selectedRowKeys.value.length
  ? t('screening.result.saveSelectedScope', { count: handoffRows.value.length, total: selectedRowKeys.value.length })
  : t('screening.result.saveScope', { count: handoffRows.value.length, total: passedRows.value.length }))
const rowSelection = computed(() => ({
  selectedRowKeys: selectedRowKeys.value,
  preserveSelectedRowKeys: true,
  onChange: (keys: Array<string | number>) => { selectedRowKeys.value = keys.map(String) }
}))
function openSaveModal(): void {
  saveSetName.value = t('screening.result.defaultSetName', { id: taskId.value.slice(0, 8) })
  saveModalOpen.value = true
}
async function projectIdForTask(): Promise<string> {
  if (taskProjectId.value) return taskProjectId.value
  const query = typeof route.query.project_id === 'string' ? route.query.project_id : ''
  if (query) return taskProjectId.value = query
  const response = await getTaskDetail(taskId.value, { silent: true })
  return taskProjectId.value = response.data.project_id ?? ''
}
async function handleSaveCandidates(): Promise<void> {
  if (savingCandidates.value || !saveSetName.value.trim() || !handoffRows.value.length) return
  const snapshot = [...handoffRows.value]
  const name = saveSetName.value.trim()
  const id = taskId.value
  const projectId = await projectIdForTask().catch(() => '')
  if (!projectId) { message.error(t('screening.result.noProject')); return }
  savingCandidates.value = true
  try {
    const candidateIds: string[] = []
    for (let offset = 0; offset < snapshot.length; offset += 20) {
      const created = await Promise.all(snapshot.slice(offset, offset + 20).map(async row => {
        const score = row.docking_score?.trim() ? Number(row.docking_score) : Number.NaN
        const result = await createCandidate(projectId, {
          candidate_type: 'SMALL_MOLECULE', source: 'SCREENING', task_id: id,
          smiles: row.smiles ?? '', ...(Number.isFinite(score) ? { design_score: score } : {}), attrs: { ...row }
        })
        return result.data.id
      }))
      candidateIds.push(...created)
    }
    const set = await createCandidateSet(projectId, {
      name, description: t('screening.result.setDescription', { id }), source_task_id: id
    })
    await addCandidateSetItems(set.data.id, { candidate_ids: candidateIds })
    message.success(t('screening.result.saved', { count: candidateIds.length }))
    saveModalOpen.value = false
    await router.push({ path: '/predict', query: { project_id: projectId, candidate_set_id: set.data.id } })
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('screening.result.saveFailed'))
  } finally { savingCandidates.value = false }
}
async function sendToAdmet(): Promise<void> {
  if (handoffBusy.value || !handoffRows.value.length) return
  handoffBusy.value = true
  const snapshot = [...handoffRows.value]
  try {
    const projectId = await projectIdForTask()
    if (!projectId) { message.error(t('screening.result.noProject')); return }
    const file = await uploadMoleculeHandoff(snapshot.map(row => ({ smiles: row.smiles ?? '', moleculeId: row.molecule_id || undefined })), `screening-${taskId.value}-admet.csv`)
    await router.push({ path: '/predict', query: { project_id: projectId, ...file } })
    message.success(t('screening.result.handoffSent', { count: snapshot.length }))
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('screening.result.handoffFailed'))
  } finally { handoffBusy.value = false }
}
function nonEmptyString(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value.trim() : ''
}
function resolveMdProvenance(detail: Task | null, fallbackProjectId: string): Record<string, string> {
  const projectId = nonEmptyString(detail?.project_id) || nonEmptyString(fallbackProjectId)
  if (!projectId) return {}
  const query: Record<string, string> = { project_id: projectId }
  const receptorSnap = (detail?.input_snapshots ?? []).find(snap =>
    /protein|receptor/i.test(String(snap.inputRole ?? '')) && snap.entityType === 'protein_structure'
  )
  const inputs = (detail?.inputs ?? {}) as Record<string, unknown>
  const targetId = nonEmptyString(receptorSnap?.detail?.target_id) || nonEmptyString(inputs.target_id)
  const proteinId = nonEmptyString(receptorSnap?.detail?.protein_id) || nonEmptyString(inputs.protein_id)
  const snapFileId = nonEmptyString(receptorSnap?.fileId)
  const rawStructureId = nonEmptyString(receptorSnap?.entityId) || nonEmptyString(receptorSnap?.detail?.structure_id) || nonEmptyString(inputs.structure_id)
  const structureId = rawStructureId && rawStructureId !== snapFileId ? rawStructureId : ''
  if (targetId) query.target_id = targetId
  if (targetId && proteinId) query.protein_id = proteinId
  if (targetId && proteinId && structureId) query.structure_id = structureId
  return query
}
async function sendToMd(): Promise<void> {
  if (mdBusy.value) return
  mdBusy.value = true
  try {
    let detail = taskDetail.value
    if (!detail && taskId.value) {
      detail = (await getTaskDetail(taskId.value, { silent: true }).catch(() => null))?.data ?? null
      taskDetail.value = detail
    }
    const projectId = await projectIdForTask().catch(() => '')
    const query = resolveMdProvenance(detail, projectId)
    if (!query.project_id) { message.error(t('screening.result.mdNoProject')); return }
    if (!query.structure_id) message.warning(t('screening.result.mdPartialContext'))
    await router.push({ path: '/md', query })
  } finally { mdBusy.value = false }
}
const NUMERIC_KEYS = ['pharmacophore_features', 'mol_weight', 'logp', 'tpsa', 'qed', 'docking_score', 'rmsd_lb', 'rmsd_ub', 'num_poses', 'rank']
function columnTitle(key: string): string {
  const suffix = SCREENING_RANKED_COLUMN_I18N[key]
  return suffix ? t(`screening.result.${suffix}`) : key
}
function isStageColumn(key: string): boolean { return ['stage_pharmacophore', 'stage_docking', 'stage_cutoff'].includes(key) }
const tableColumns = computed(() => [
  { title: t('screening.result.poseAction'), key: 'pose', width: 160 },
  ...SCREENING_RANKED_COLUMNS.map(key => ({
    title: columnTitle(key), dataIndex: key, key,
    width: key === 'smiles' || key === 'error' ? 220 : 120,
    align: NUMERIC_KEYS.includes(key) ? 'right' as const : 'left' as const,
    sorter: NUMERIC_KEYS.includes(key) ? (a: CsvPreviewRow, b: CsvPreviewRow) => {
      const av = a[key]?.trim() ? Number(a[key]) : Number.NaN
      const bv = b[key]?.trim() ? Number(b[key]) : Number.NaN
      return (Number.isFinite(av) ? av : Infinity) - (Number.isFinite(bv) ? bv : Infinity)
    } : undefined
  }))
])
const exportColumns = computed(() => SCREENING_RANKED_COLUMNS.map(key => ({ key, title: columnTitle(key) })))
const funnelStages = computed(() => funnelFromRankedRows(rows.value))
const keptCount = computed(() => countPasses(rows.value))
const stageLabels = computed<Record<FunnelStageKey, string>>(() => ({
  input: t('screening.result.stageInput'), pharmacophore: t('screening.result.stagePharmacophore'),
  docking: t('screening.result.stageDocking'), cutoff: t('screening.result.stageCutoff'), kept: t('screening.result.stageKept')
}))
const stageRows = computed(() => funnelStages.value.map((stage, index) => {
  const previous = index === 0 ? stage.remaining : funnelStages.value[index - 1]?.remaining ?? stage.remaining
  return { key: stage.key, label: stageLabels.value[stage.key], remaining: stage.remaining, eliminated: index === 0 ? 0 : previous - stage.remaining }
}))
function validRank(record: CsvPreviewRow): boolean {
  const value = Number(record.rank)
  return Number.isInteger(value) && value > 0
}
function canViewPose(record: CsvPreviewRow): boolean {
  return validRank(record) && isTruthyFlag(record.passes)
}
function openPose(record: CsvPreviewRow): void {
  if (canViewPose(record)) void router.push({ path: `/docking-results/pose-${Number(record.rank)}`, query: { task_id: taskId.value } })
}
function handleExport(): void { downloadCsv(`screening-${taskId.value}.csv`, exportColumns.value, rows.value) }
let requestId = 0
async function load(): Promise<void> {
  const id = taskId.value
  const request = ++requestId
  loading.value = true; errorMessage.value = ''; rows.value = []; selectedRowKeys.value = []; taskProjectId.value = ''; taskDetail.value = null
  try {
    const data = await loadMoleculeTable(id)
    if (request !== requestId) return
    rows.value = data.rows
    taskProjectId.value = data.detail.project_id ?? ''
    void getTaskDetail(id, { silent: true }).then(res => { if (request === requestId) taskDetail.value = res.data }).catch(() => undefined)
  } catch (error) {
    if (request === requestId) errorMessage.value = error instanceof Error ? error.message : t('screening.result.loadFailed')
  } finally { if (request === requestId) loading.value = false }
}
watch(taskId, () => { void load() }, { immediate: true })
</script>

<template>
  <main class="screen-result" data-testid="screen-result-page">
    <AppPageHeader :title="t('screening.result.title')" :subtitle="t('screening.result.subtitle')">
      <template #actions><a-space>
        <a-button :disabled="!handoffRows.length" data-testid="screen-save-candidates" @click="openSaveModal">{{ selectedRowKeys.length ? t('screening.result.saveSelected', { count: handoffRows.length }) : t('screening.result.saveCandidates') }}</a-button>
        <a-button :disabled="!handoffRows.length" :loading="handoffBusy" data-testid="screen-send-admet" @click="sendToAdmet">{{ t('screening.result.sendAdmet', { count: handoffRows.length }) }}</a-button>
        <a-button :disabled="!rows.length" :loading="mdBusy" data-testid="screen-send-md" @click="sendToMd">{{ t('screening.result.useReceptorMd') }}</a-button>
        <a-button type="primary" :disabled="!rows.length" data-testid="screen-result-export" @click="handleExport">{{ t('screening.result.exportCsv') }}</a-button>
      </a-space></template>
    </AppPageHeader>
    <TaskContextBar :task-id="taskId" active="result" :result-path="route.fullPath" />
    <a-alert v-if="errorMessage" type="error" show-icon data-testid="screen-result-error" :message="errorMessage" />
    <div v-if="loading" data-testid="screen-result-loading"><a-spin /> {{ t('screening.result.loading') }}</div>
    <a-empty v-else-if="!errorMessage && !rows.length" data-testid="screen-result-empty" :description="t('screening.result.empty')" />
    <template v-else-if="!errorMessage">
      <a-row :gutter="16">
        <a-col :xs="24" :lg="12"><a-card :title="t('screening.result.funnel')" data-testid="screen-result-funnel"><FunnelChart :stages="funnelStages" :labels="stageLabels" /></a-card></a-col>
        <a-col :xs="24" :lg="12"><a-card :title="t('screening.result.stats')"><a-statistic :title="t('screening.result.count')" :value="rows.length" /><a-statistic :title="t('screening.result.kept')" :value="keptCount" /><a-table :columns="[{ title: '', dataIndex: 'label', key: 'label' }, { title: t('screening.result.passed'), dataIndex: 'remaining', key: 'remaining', align: 'right' }, { title: t('screening.result.eliminated'), dataIndex: 'eliminated', key: 'eliminated', align: 'right' }]" :data-source="stageRows" :pagination="false" row-key="key" size="small" /></a-card></a-col>
      </a-row>
      <a-alert v-if="rows.length && !passedRows.length" type="info" show-icon data-testid="screen-zero-pass-alert" :message="t('screening.result.zeroPassNotice')" />
      <a-card :title="t('screening.result.table')">
        <a-table :columns="tableColumns" :data-source="rows" :row-selection="rowSelection" :pagination="{ pageSize: 20, showSizeChanger: true }" :scroll="{ x: 'max-content' }" :row-key="rowStableKey" size="small" data-testid="screen-result-table">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'pose'">
              <a-button v-if="canViewPose(record)" size="small" data-testid="screen-view-pose" @click="openPose(record)">{{ t('screening.result.viewPose') }}</a-button>
              <span v-else>{{ t('screening.result.poseNotExported') }}</span>
            </template>
            <template v-else-if="column.key === 'passes' || isStageColumn(column.key)">
              <a-tag :color="isTruthyFlag(record[column.key]) ? 'green' : 'default'">{{ isTruthyFlag(record[column.key]) ? t('screening.result.yes') : t('screening.result.no') }}</a-tag>
            </template>
          </template>
        </a-table>
      </a-card>
    </template>
    <a-modal v-model:open="saveModalOpen" :title="t('screening.result.saveCandidates')" :confirm-loading="savingCandidates" :ok-text="t('screening.result.saveButton')" data-testid="screen-save-candidates-modal" @ok="handleSaveCandidates"><a-form layout="vertical"><a-form-item :label="t('screening.result.setName')" required><a-input v-model:value="saveSetName" :placeholder="t('screening.result.setNamePlaceholder')" /></a-form-item><p>{{ saveScopeText }}</p></a-form></a-modal>
  </main>
  <ResultDisclaimer />
</template>

<style scoped lang="less">
.screen-result { display: flex; flex-direction: column; gap: 16px; padding: 24px; }
</style>
