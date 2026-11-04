<template>
  <main class="results-page" data-testid="generation-results-page">
    <AppPageHeader :title="t('design.results.title')" :subtitle="t('design.results.subtitle')">
      <template #actions>
        <a-space>
          <a-button data-testid="results-back-task" @click="goTaskDetail">
            {{ t('design.results.viewTask') }}
          </a-button>
          <a-button
            type="primary"
            :disabled="!canSave"
            data-testid="results-save-set"
            @click="openSaveModal"
          >
            {{ t('design.results.saveToSet') }}
          </a-button>
        </a-space>
      </template>
    </AppPageHeader>


    <a-alert
      v-if="loadError"
      type="error"
      show-icon
      :message="t('design.results.loadFailed')"
      data-testid="results-load-error"
    />

    <section v-if="!isTerminal" class="results-progress" data-testid="results-progress">
      <a-progress :percent="progressPercent" status="active" />
      <p class="results-progress__text">
        {{ t('design.results.statusLabel') }}：{{ statusText }}
        <span v-if="progressMessage"> · {{ progressMessage }}</span>
      </p>
    </section>

    <a-alert
      v-if="isFailure"
      type="error"
      show-icon
      :message="t('design.results.taskFailed')"
      :description="detail?.error_message ?? undefined"
      data-testid="results-task-failed"
    />

    <template v-if="isTerminal && !isFailure">
      <section class="results-summary" data-testid="results-summary">
        <span class="results-summary__count">
          {{ isPeptideResult
            ? t('design.results.peptideCount', { count: rows.length })
            : t('design.results.moleculeCount', { count: rows.length }) }}
        </span>
      </section>

      <a-alert
        v-if="tableMissing"
        type="warning"
        show-icon
        :message="t('design.results.tableMissing')"
        data-testid="results-table-missing"
      />

      <template v-if="columns.length">
        <section class="results-filters" data-testid="results-filters">
          <div class="results-filters__sort">
            <span class="results-filters__label">{{ t('design.results.sortBy') }}</span>
            <a-select v-model:value="sortKey" class="filter-control" data-testid="results-sort-key">
              <a-select-option v-for="column in numericColumns" :key="column.key" :value="column.key">
                {{ column.title }}
              </a-select-option>
            </a-select>
            <a-radio-group v-model:value="sortOrder" button-style="solid" size="small">
              <a-radio-button value="desc">{{ t('design.results.desc') }}</a-radio-button>
              <a-radio-button value="asc">{{ t('design.results.asc') }}</a-radio-button>
            </a-radio-group>
          </div>

          <div class="results-filters__range">
            <template v-if="scoreColumn">
              <span class="results-filters__label">{{ scoreColumn.title }}</span>
              <a-input-number
                v-model:value="filters.scoreMin"
                class="filter-control filter-control--num"
                :placeholder="t('design.results.min')"
                data-testid="results-score-min"
              />
              <span class="results-filters__dash">~</span>
              <a-input-number
                v-model:value="filters.scoreMax"
                class="filter-control filter-control--num"
                :placeholder="t('design.results.max')"
                data-testid="results-score-max"
              />
            </template>
            <template v-if="mwColumn">
              <span class="results-filters__label">{{ mwColumn.title }}</span>
              <a-input-number
                v-model:value="filters.mwMin"
                class="filter-control filter-control--num"
                :placeholder="t('design.results.min')"
              />
              <span class="results-filters__dash">~</span>
              <a-input-number
                v-model:value="filters.mwMax"
                class="filter-control filter-control--num"
                :placeholder="t('design.results.max')"
              />
            </template>
            <template v-if="qedColumn">
              <span class="results-filters__label">{{ qedColumn.title }}</span>
              <a-input-number
                v-model:value="filters.qedMin"
                class="filter-control filter-control--num"
                :placeholder="t('design.results.min')"
              />
            </template>
            <a-button size="small" @click="resetFilters">{{ t('design.results.reset') }}</a-button>
          </div>
        </section>

        <div class="molecule-grid" data-testid="molecule-grid">
          <article
            v-for="row in pagedRows"
            :key="row.__rowKey"
            class="molecule-card"
            data-testid="molecule-card"
          >
            <div class="molecule-card__structure">
              <Smiles2DCell v-if="rowSmiles(row)" :smiles="rowSmiles(row)" :width="200" :height="140" />
              <div v-else class="molecule-card__sequence">{{ rowSequence(row) || '-' }}</div>
            </div>
            <dl class="molecule-card__metrics">
              <div v-for="metric in rowMetrics(row)" :key="metric.key" class="molecule-card__metric">
                <dt>{{ metric.label }}</dt>
                <dd>{{ metric.value }}</dd>
              </div>
            </dl>
          </article>
        </div>

        <div v-if="!pagedRows.length" class="results-empty">{{ t('design.results.empty') }}</div>

        <a-pagination
          v-if="sortedRows.length > pageSize"
          v-model:current="currentPage"
          class="results-pagination"
          :total="sortedRows.length"
          :page-size="pageSize"
          :show-size-changer="false"
        />
      </template>
    </template>

    <a-modal
      v-model:open="saveModalOpen"
      :title="t('design.results.saveToSet')"
      :confirm-loading="saving"
      data-testid="results-save-modal"
      @ok="handleSave"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('design.results.setName')">
          <a-input v-model:value="setName" data-testid="results-set-name" />
        </a-form-item>
        <p class="save-hint">{{ t('design.results.saveHint', { count: saveableRows.length }) }}</p>
      </a-form>
    </a-modal>
  </main>
</template>

<script setup lang="ts">
import { formatNumber } from '@/domain/common/format'
  import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import Smiles2DCell from '@/components/tasks/Smiles2DCell.vue'
  import {
    findMoleculeTableArtifact,
    getDesignGenerationResult,
    loadDesignTable,
  } from '@/api/design'
  import { openTaskEventStream, type TaskEventStreamHandle } from '@/api/task-events'
  import {
    addCandidateSetItems,
    createCandidate,
    createCandidateSet,
  } from '@/api/compounds'
  import { getTaskDetail, isTaskTerminalStatus } from '@/api/tasks'
  import type { CandidateCreateInput } from '@/types/compounds'
  import type { DesignGenerationResult, DesignTableColumn, DesignTableRow } from '@/types/design'
  import type { TaskStatus } from '@/types/models'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()

  const taskId = computed(() => String(route.params.id ?? ''))

  const detail = ref<DesignGenerationResult | null>(null)
  const loadError = ref(false)
  const tableMissing = ref(false)
  const loadingTable = ref(false)
  const columns = ref<DesignTableColumn[]>([])
  const rows = ref<DesignTableRow[]>([])

  const status = ref<TaskStatus | null>(null)
  const progressPercent = ref(0)
  const progressMessage = ref<string | null>(null)

  const filters = reactive<{
    scoreMin: number | null
    scoreMax: number | null
    mwMin: number | null
    mwMax: number | null
    qedMin: number | null
  }>({
    scoreMin: null,
    scoreMax: null,
    mwMin: null,
    mwMax: null,
    qedMin: null,
  })

  const sortKey = ref('')
  const sortOrder = ref<'asc' | 'desc'>('desc')
  const currentPage = ref(1)
  const pageSize = 24

  const saveModalOpen = ref(false)
  const saving = ref(false)
  const setName = ref('')

  let stream: TaskEventStreamHandle | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null

  const isTerminal = computed(() => (status.value ? isTaskTerminalStatus(status.value) : false))
  const isFailure = computed(() => status.value === 'failure' || status.value === 'canceled')

  const statusText = computed(() => {
    switch (status.value) {
      case 'success':
        return t('design.status.success')
      case 'failure':
        return t('design.status.failure')
      case 'canceled':
        return t('design.status.canceled')
      case 'running':
        return t('design.status.running')
      case 'pending':
        return t('design.status.pending')
      default:
        return '-'
    }
  })

  function findColumn(patterns: RegExp[]): DesignTableColumn | undefined {
    return columns.value.find(
      (column) => patterns.some((pattern) => pattern.test(column.key) || pattern.test(column.title))
    )
  }

  const scoreColumn = computed(() => findColumn([/score/i, /评分/i]))
  const mwColumn = computed(() => findColumn([/^mw$/i, /molecular_weight/i, /分子量/i]))
  const logpColumn = computed(() => findColumn([/logp/i, /xlogp/i, /脂水/i]))
  const qedColumn = computed(() => findColumn([/qed/i]))
  const smilesColumn = computed(() => findColumn([/smiles/i]))
  const sequenceColumn = computed(() => findColumn([/sequence/i, /序列/i]))
  const isPeptideResult = computed(() => Boolean(sequenceColumn.value) && !smilesColumn.value)

  const numericColumns = computed(() => columns.value.filter((column) => column.numeric))

  function numericValue(row: DesignTableRow, key: string | undefined): number | null {
    if (!key) {
      return null
    }
    const raw = (row[key] ?? '').trim()
    if (!raw) {
      return null
    }
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  }

  const filteredRows = computed(() => {
    return rows.value.filter((row) => {
      const score = numericValue(row, scoreColumn.value?.key)
      const mw = numericValue(row, mwColumn.value?.key)
      const qed = numericValue(row, qedColumn.value?.key)
      if (filters.scoreMin !== null && (score === null || score < filters.scoreMin)) return false
      if (filters.scoreMax !== null && (score === null || score > filters.scoreMax)) return false
      if (filters.mwMin !== null && (mw === null || mw < filters.mwMin)) return false
      if (filters.mwMax !== null && (mw === null || mw > filters.mwMax)) return false
      if (filters.qedMin !== null && (qed === null || qed < filters.qedMin)) return false
      return true
    })
  })

  const sortedRows = computed(() => {
    const key = sortKey.value
    if (!key) {
      return filteredRows.value
    }
    const direction = sortOrder.value === 'asc' ? 1 : -1
    return [...filteredRows.value].sort((a, b) => {
      const av = numericValue(a, key)
      const bv = numericValue(b, key)
      if (av === null && bv === null) return 0
      if (av === null) return 1
      if (bv === null) return -1
      return (av - bv) * direction
    })
  })

  const pagedRows = computed(() => {
    const start = (currentPage.value - 1) * pageSize
    return sortedRows.value.slice(start, start + pageSize)
  })

  const saveableRows = computed(() =>
    sortedRows.value.filter((row) => rowSmiles(row) || rowSequence(row))
  )

  const canSave = computed(
    () => isTerminal.value && !isFailure.value && saveableRows.value.length > 0
  )

  function rowSmiles(row: DesignTableRow): string {
    return smilesColumn.value ? (row[smilesColumn.value.key] ?? '').trim() : ''
  }

  function rowSequence(row: DesignTableRow): string {
    return sequenceColumn.value ? (row[sequenceColumn.value.key] ?? '').trim() : ''
  }

  function formatMetric(raw: string | undefined): string {
    const value = Number((raw ?? '').trim())
    if (!Number.isFinite(value)) {
      return raw && raw.trim() !== '' ? raw : '-'
    }
    return formatNumber(value, 3)
  }

  function rowMetrics(row: DesignTableRow): Array<{ key: string; label: string; value: string }> {
    const entries: Array<{ key: string; label: string; value: string }> = []
    const defs: Array<[DesignTableColumn | undefined, string]> = [
      [scoreColumn.value, 'score'],
      [mwColumn.value, 'mw'],
      [logpColumn.value, 'logp'],
      [qedColumn.value, 'qed'],
    ]
    for (const [column, tag] of defs) {
      if (column) {
        entries.push({ key: tag, label: column.title, value: formatMetric(row[column.key]) })
      }
    }
    if (isPeptideResult.value) {
      for (const column of numericColumns.value) {
        if (column.key === scoreColumn.value?.key || column.key === 'length') {
          continue
        }
        entries.push({
          key: column.key,
          label: column.title,
          value: formatMetric(row[column.key]),
        })
      }
    }
    return entries
  }

  function resetFilters(): void {
    filters.scoreMin = null
    filters.scoreMax = null
    filters.mwMin = null
    filters.mwMax = null
    filters.qedMin = null
  }

  function initializeSort(): void {
    if (sortKey.value) {
      return
    }
    sortKey.value = scoreColumn.value?.key ?? numericColumns.value[0]?.key ?? ''
  }

  async function loadResult(): Promise<void> {
    if (!taskId.value) {
      return
    }
    try {
      const result = await getDesignGenerationResult(taskId.value)
      detail.value = result
      status.value = result.status
      if (result.status === 'running' || result.status === 'pending') {
        startTracking()
        return
      }
      if (result.status === 'success') {
        await loadTable(result)
      }
    } catch {
      // 结果尚未生成时后端可能返回 404，转为追踪任务状态。
      startTracking()
    }
  }

  async function loadTable(result: DesignGenerationResult): Promise<void> {
    const table = findMoleculeTableArtifact(result)
    if (!table) {
      tableMissing.value = true
      return
    }
    loadingTable.value = true
    try {
      const parsed = await loadDesignTable(table)
      columns.value = parsed.columns
      rows.value = parsed.rows
      initializeSort()
    } catch {
      tableMissing.value = true
    } finally {
      loadingTable.value = false
    }
  }

  function applyProgress(payload: {
    status: TaskStatus | null
    progress: number
    progressMessage: string | null
    terminal: boolean
  }): void {
    if (payload.status) {
      status.value = payload.status
    }
    progressPercent.value = Math.max(0, Math.min(100, Math.round(payload.progress)))
    progressMessage.value = payload.progressMessage
    if (payload.terminal) {
      stopTracking()
      void loadResult()
    }
  }

  function startTracking(): void {
    if (stream || pollTimer) {
      return
    }
    stream = openTaskEventStream(taskId.value, {
      onSnapshot: applyProgress,
      onStatus: applyProgress,
      onProgress: applyProgress,
      onDone: applyProgress,
      onError: () => {
        startPolling()
      },
    })
    if (!stream.available) {
      startPolling()
    }
  }

  function startPolling(): void {
    if (pollTimer) {
      return
    }
    pollTimer = setInterval(async () => {
      try {
        const response = await getTaskDetail(taskId.value)
        progressPercent.value = Math.max(0, Math.min(100, Math.round(response.data.progress ?? 0)))
        progressMessage.value = response.data.progress_message ?? null
        status.value = response.data.status
        if (isTaskTerminalStatus(response.data.status)) {
          stopTracking()
          await loadResult()
        }
      } catch {
        // 轮询失败时继续等待下一次。
      }
    }, 5000)
  }

  function stopTracking(): void {
    stream?.close()
    stream = null
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function openSaveModal(): void {
    setName.value = t('design.results.defaultSetName', {
      id: taskId.value.slice(0, 8),
    })
    saveModalOpen.value = true
  }

  async function handleSave(): Promise<void> {
    const projectId = detail.value?.project_id
    if (!projectId) {
      message.warning(t('design.results.noProject'))
      return
    }
    if (!setName.value.trim()) {
      message.warning(t('design.results.setNameRequired'))
      return
    }
    if (!saveableRows.value.length) {
      message.warning(t('design.results.nothingToSave'))
      return
    }

    saving.value = true
    try {
      const candidateIds = await Promise.all(
        saveableRows.value.map(async (row) => {
          const smiles = rowSmiles(row)
          const sequence = rowSequence(row)
          const payload: CandidateCreateInput = {
            candidate_type: smiles ? 'SMALL_MOLECULE' : 'PEPTIDE',
            source: 'DESIGN',
            task_id: taskId.value,
            ...(smiles ? { smiles } : {}),
            ...(sequence ? { peptide_sequence: sequence } : {}),
            design_score: numericValue(row, scoreColumn.value?.key) ?? undefined,
            attrs: { ...row },
          }
          const created = await createCandidate(projectId, payload)
          return created.data.id
        })
      )

      const set = await createCandidateSet(projectId, {
        name: setName.value.trim(),
        description: t('design.results.setDescription', { id: taskId.value }),
        source_task_id: taskId.value,
      })
      await addCandidateSetItems(set.data.id, { candidate_ids: candidateIds })

      message.success(t('design.results.saved', { count: candidateIds.length }))
      saveModalOpen.value = false
    } catch {
      message.error(t('design.results.saveFailed'))
    } finally {
      saving.value = false
    }
  }

  function goTaskDetail(): void {
    void router.push({ name: 'TaskDetail', params: { id: taskId.value } })
  }

  onMounted(() => {
    void loadResult()
  })

  onBeforeUnmount(() => {
    stopTracking()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .results-page {
    max-width: 1200px;
    margin: 0 auto;
    padding: 32px 24px 48px;
  }

  .results-progress {
    margin-bottom: 24px;
    padding: 20px;
    border: 1px solid @border-color;
    border-radius: 8px;
    background: @bg-surface;
  }

  .results-progress__text {
    margin: 8px 0 0;
    color: @text-secondary;
  }

  .results-summary {
    margin-bottom: 16px;
  }

  .results-summary__count {
    font-size: 18px;
    font-weight: 600;
  }

  .results-filters {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-bottom: 20px;
    padding: 16px;
    border: 1px solid @border-color;
    border-radius: 8px;
    background: @surface-sunken;
  }

  .results-filters__sort,
  .results-filters__range {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }

  .results-filters__label {
    font-weight: 500;
    color: @text-secondary;
  }

  .results-filters__dash {
    color: @text-tertiary;
  }

  .filter-control {
    min-width: 140px;
  }

  .filter-control--num {
    width: 110px;
  }

  .molecule-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 16px;
  }

  .molecule-card {
    display: flex;
    flex-direction: column;
    border: 1px solid @border-color;
    border-radius: 8px;
    overflow: hidden;
    background: @bg-surface;
    transition: box-shadow 0.2s ease;
  }

  .molecule-card:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  }

  .molecule-card__structure {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 140px;
    padding: 12px;
    background: @surface-sunken;
  }

  .molecule-card__sequence {
    font-family: monospace;
    font-size: 12px;
    color: @text-secondary;
    word-break: break-all;
    text-align: center;
  }

  .molecule-card__metrics {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    margin: 0;
    padding: 12px 16px 16px;
  }

  .molecule-card__metric dt {
    font-size: 12px;
    color: @text-tertiary;
  }

  .molecule-card__metric dd {
    margin: 2px 0 0;
    font-weight: 600;
    color: @text-primary;
  }

  .results-empty {
    padding: 48px 0;
    text-align: center;
    color: @text-tertiary;
  }

  .results-pagination {
    margin-top: 24px;
    text-align: right;
  }

  .save-hint {
    margin: 0;
    color: @text-tertiary;
  }
</style>
