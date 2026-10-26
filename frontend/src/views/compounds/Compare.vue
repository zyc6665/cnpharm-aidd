<template>
  <main class="candidate-compare-page">
    <router-link :to="`/projects/${projectId}`" class="back-link">
      {{ t('compounds.backToProject') }}
    </router-link>
    <ProjectWorkspaceNav :project-id="projectId" />

    <AppPageHeader :title="t('candidates.compare.title')" :subtitle="t('candidates.compare.subtitle')">
      <template #actions>
        <a-space>
          <span class="selected-counter" data-testid="compare-selected-counter">
            {{ t('candidates.compare.selected', { count: selected.length, max: MAX_COMPARE_CANDIDATES }) }}
          </span>
          <a-button
            :disabled="selected.length === 0"
            data-testid="compare-clear"
            @click="clearSelection"
          >
            {{ t('candidates.compare.clear') }}
          </a-button>
          <a-button
            type="primary"
            :disabled="selected.length === 0"
            data-testid="compare-export"
            @click="exportCsv"
          >
            {{ t('candidates.compare.exportCsv') }}
          </a-button>
        </a-space>
      </template>
    </AppPageHeader>

    <a-alert
      v-if="limitReached"
      class="compare-alert"
      type="warning"
      show-icon
      data-testid="compare-limit-hint"
      :message="t('candidates.compare.limitHint')"
    />

    <a-alert
      v-if="loadError"
      class="compare-alert"
      type="error"
      show-icon
      data-testid="compare-error"
      :message="t('compounds.errors.loadCandidates')"
    >
      <template #action>
        <a-button size="small" @click="loadCandidates">{{ t('common.refresh') }}</a-button>
      </template>
    </a-alert>

    <SkeletonList v-if="loading && candidates.length === 0" :count="5" />

    <a-row v-else :gutter="24">
      <a-col :xs="24" :md="8">
        <section class="picker-panel">
          <h3 class="section-title">{{ t('candidates.compare.pickHint') }}</h3>
          <ul class="picker-list" data-testid="compare-picker-list">
            <li v-for="candidate in candidates" :key="candidate.id" class="picker-item">
              <div class="picker-meta">
                <router-link :to="candidateRoute(candidate.id)" class="picker-name">
                  {{ candidateTitle(candidate) }}
                </router-link>
                <a-tag>{{ t(candidateLocationLabel(candidate)) }}</a-tag>
              </div>
              <a-button
                size="small"
                :disabled="isSelected(candidate.id) || limitReached"
                data-testid="compare-add"
                @click="addCandidate(candidate)"
              >
                {{ isSelected(candidate.id) ? t('candidates.compare.remove') : t('candidates.compare.add') }}
              </a-button>
            </li>
          </ul>
          <p v-if="candidates.length === 0" class="section-empty">
            {{ t('compounds.empty.candidates') }}
          </p>
        </section>
      </a-col>

      <a-col :xs="24" :md="16">
        <section class="matrix-panel">
          <a-table
            v-if="matrix.columns.length > 0"
            :columns="matrixColumns"
            :data-source="matrixRows"
            :pagination="false"
            row-key="key"
            size="small"
            :scroll="{ x: 640 }"
            data-testid="compare-matrix"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'label'">
                {{ t(record.labelKey) }}
              </template>
              <template v-else>
                <span
                  :class="['matrix-cell', { 'matrix-cell-diff': record.highlight[column.index] }]"
                  :data-testid="`compare-cell-${record.key}-${column.index}`"
                >
                  {{ record.values[column.index] }}
                </span>
              </template>
            </template>
          </a-table>
          <p v-else class="section-empty" data-testid="compare-empty">
            {{ t('candidates.compare.empty') }}
          </p>
        </section>
      </a-col>
    </a-row>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
  import { compareCandidates, listCandidates } from '@/api/compounds'
  import {
    MAX_COMPARE_CANDIDATES,
    buildComparisonMatrix,
    canAddToComparison,
    candidateLocationLabel
  } from '@/domain/compounds'
  import type { Candidate, ComparisonPropertySource } from '@/types/compounds'

  interface MatrixColumn {
    title: string
    key: string
    index: number
    width: number
  }

  interface MatrixRow {
    key: string
    labelKey: string
    values: string[]
    highlight: boolean[]
  }

  const route = useRoute()
  const { t } = useI18n()

  const projectId = computed(() => String(route.params.projectId || ''))

  /** 候选物详情页需要 `project_id` 才能渲染「返回数据资产」。 */
  function candidateRoute(candidateId: string): string {
    const base = `/candidates/${encodeURIComponent(candidateId)}`
    return projectId.value ? `${base}?project_id=${encodeURIComponent(projectId.value)}` : base
  }

  const loading = ref(false)
  const loadError = ref(false)
  const candidates = ref<Candidate[]>([])
  const selectedIds = ref<string[]>([])
  const comparisonItems = ref<ComparisonPropertySource[]>([])

  const selected = computed(() =>
    selectedIds.value
      .map(id => candidates.value.find(candidate => candidate.id === id))
      .filter((candidate): candidate is Candidate => Boolean(candidate))
  )

  const limitReached = computed(
    () => !canAddToComparison(selected.value.length, MAX_COMPARE_CANDIDATES)
  )

  /**
   * 对比矩阵的数据源：优先用 `POST /candidates:compare` 摊平后的 7 项性质
   * （后端会用 ECFP4 统一计算，避免前端内联 compound 缺失时的空值），
   * 接口未返回或数量对不上时回退到列表里的候选物。
   */
  const comparisonSources = computed<ComparisonPropertySource[]>(() =>
    comparisonItems.value.length === selected.value.length && comparisonItems.value.length > 0
      ? comparisonItems.value
      : selected.value
  )

  const matrix = computed(() => buildComparisonMatrix(comparisonSources.value))

  const matrixColumns = computed<MatrixColumn[]>(() => [
    { title: t('candidates.compare.rowHeader'), key: 'label', index: -1, width: 160 },
    ...matrix.value.columns.map((column, index) => ({
      title: column.label,
      key: column.id,
      index,
      width: 120
    }))
  ])

  const matrixRows = computed<MatrixRow[]>(() =>
    matrix.value.rows.map(row => ({
      key: row.key,
      labelKey: row.labelKey,
      values: row.values,
      highlight: row.highlight
    }))
  )

  function candidateTitle(candidate: Candidate): string {
    return candidate.name || candidate.code || candidate.peptide_sequence || candidate.id
  }

  function isSelected(candidateId: string): boolean {
    return selectedIds.value.includes(candidateId)
  }

  function addCandidate(candidate: Candidate): void {
    if (isSelected(candidate.id)) {
      selectedIds.value = selectedIds.value.filter(id => id !== candidate.id)
      return
    }

    if (limitReached.value) {
      message.warning(t('candidates.compare.limitHint'))
      return
    }

    selectedIds.value = [...selectedIds.value, candidate.id]
  }

  function clearSelection(): void {
    selectedIds.value = []
  }

  function escapeCsvCell(value: string): string {
    if (value.includes(',') || value.includes('"') || value.includes('\n')) {
      return `"${value.replace(/"/g, '""')}"`
    }
    return value
  }

  function buildCsv(): string {
    if (selected.value.length === 0) {
      return ''
    }

    const header = [
      t('candidates.compare.rowHeader'),
      ...matrix.value.columns.map(column => escapeCsvCell(column.label))
    ].join(',')

    const lines = matrix.value.rows.map(row =>
      [t(row.labelKey), ...row.values.map(value => escapeCsvCell(value))].join(',')
    )

    return [header, ...lines].join('\n')
  }

  function exportCsv(): void {
    const csv = buildCsv()
    if (!csv) {
      message.warning(t('candidates.compare.exportEmpty'))
      return
    }

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    try {
      anchor.href = url
      anchor.download = 'candidate-comparison.csv'
      document.body.appendChild(anchor)
      anchor.click()
    } finally {
      anchor.remove()
      URL.revokeObjectURL(url)
    }
  }

  async function loadComparison(): Promise<void> {
    if (!projectId.value || selectedIds.value.length === 0) {
      comparisonItems.value = []
      return
    }

    try {
      const response = await compareCandidates(projectId.value, [...selectedIds.value])
      comparisonItems.value = response.data.items
    } catch {
      comparisonItems.value = []
    }
  }

  watch(selectedIds, () => {
    void loadComparison()
  })

  async function loadCandidates(): Promise<void> {
    if (!projectId.value) return

    loading.value = true
    loadError.value = false
    try {
      const response = await listCandidates(projectId.value, { page: 1, page_size: 200 })
      candidates.value = response.data.items
      selectedIds.value = selectedIds.value.filter(id =>
        response.data.items.some(candidate => candidate.id === id)
      )
    } catch {
      loadError.value = true
      candidates.value = []
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    void loadCandidates()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .candidate-compare-page {
    max-width: 1240px;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .back-link {
    display: inline-block;
    margin-bottom: @spacing-lg;
    color: @text-tertiary;
  }

  .compare-alert {
    margin-bottom: @spacing-md;
  }

  .selected-counter {
    color: @text-secondary;
    font-size: @font-size-sm;
  }

  .picker-panel,
  .matrix-panel {
    padding: @spacing-md;
    background: @bg-surface;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
  }

  .section-title {
    margin: 0 0 @spacing-md;
    color: @text-primary;
    font-size: @font-size-sm;
  }

  .picker-list {
    max-height: 520px;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    list-style: none;
  }

  .picker-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;
    padding: @spacing-sm 0;
    border-bottom: 1px solid @border-color;
  }

  .picker-meta {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    min-width: 0;
  }

  .picker-name {
    overflow: hidden;
    color: @primary-color;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .section-empty {
    padding: @spacing-lg;
    color: @text-tertiary;
    text-align: center;
    background: @bg-surface;
    border: 1px dashed @border-color;
    border-radius: @border-radius-md;
  }

  .matrix-cell {
    font-family: @font-family-mono;
    font-size: @font-size-xs;
  }

  .matrix-cell-diff {
    display: inline-block;
    padding: 0 @spacing-xs;
    color: @warning-color;
    background: @warning-color-light;
    border-radius: @border-radius-sm;
  }
</style>
