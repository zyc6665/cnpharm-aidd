<template>
  <main class="results-page" data-testid="generation-results-page">
    <AppPageHeader :title="t('design.results.title')" :subtitle="t('design.results.subtitle')">
      <template #actions>
        <a-button
          type="primary"
          :disabled="!canSave"
          data-testid="results-save-set"
          @click="openSaveModal('all')"
        >
          {{ t('design.results.saveToSet') }}
        </a-button>
      </template>
    </AppPageHeader>

    <TaskContextBar :task-id="taskId" active="result" :result-path="route.fullPath" />

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
          <div class="results-filters__search">
            <a-input
              v-model:value="search"
              class="results-filters__search-input"
              :placeholder="t('design.results.searchPlaceholder')"
              allow-clear
              data-testid="results-search-input"
            />
            <a-button v-if="!numericColumns.length" size="small" @click="resetFilters">
              {{ t('design.results.reset') }}
            </a-button>
          </div>

          <div v-if="numericColumns.length" class="results-filters__sort">
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
            <a-button size="small" @click="resetFilters">{{ t('design.results.reset') }}</a-button>
          </div>

          <div v-if="hasRangeFilters" class="results-filters__sliders" data-testid="results-range-filters">
            <div v-if="mwColumn" class="filter-slider">
              <span class="results-filters__label">{{ mwColumn.title }}</span>
              <a-slider
                v-model:value="mwRange"
                range
                class="filter-slider__control"
                :min="mwBounds.min"
                :max="mwBounds.max"
                :step="mwBounds.step"
                data-testid="results-mw-range"
              />
              <span class="filter-slider__readout">
                {{ t('design.results.filters.range', { min: mwRange[0], max: mwRange[1] }) }}
              </span>
            </div>

            <div v-if="logpColumn" class="filter-slider">
              <span class="results-filters__label">{{ logpColumn.title }}</span>
              <a-slider
                v-model:value="logpRange"
                range
                class="filter-slider__control"
                :min="logpBounds.min"
                :max="logpBounds.max"
                :step="logpBounds.step"
                data-testid="results-logp-range"
              />
              <span class="filter-slider__readout">
                {{ t('design.results.filters.range', { min: logpRange[0], max: logpRange[1] }) }}
              </span>
            </div>

            <div v-if="hbdColumn" class="filter-slider">
              <span class="results-filters__label">{{ hbdColumn.title }}</span>
              <a-slider
                v-model:value="hbdRange"
                range
                class="filter-slider__control"
                :min="hbdBounds.min"
                :max="hbdBounds.max"
                :step="hbdBounds.step"
                data-testid="results-hbd-range"
              />
              <span class="filter-slider__readout">
                {{ t('design.results.filters.range', { min: hbdRange[0], max: hbdRange[1] }) }}
              </span>
            </div>

            <div v-if="hbaColumn" class="filter-slider">
              <span class="results-filters__label">{{ hbaColumn.title }}</span>
              <a-slider
                v-model:value="hbaRange"
                range
                class="filter-slider__control"
                :min="hbaBounds.min"
                :max="hbaBounds.max"
                :step="hbaBounds.step"
                data-testid="results-hba-range"
              />
              <span class="filter-slider__readout">
                {{ t('design.results.filters.range', { min: hbaRange[0], max: hbaRange[1] }) }}
              </span>
            </div>

            <div v-if="qedColumn" class="filter-slider filter-slider--inline">
              <span class="results-filters__label">{{ t('design.results.filters.qedMin') }}</span>
              <a-input-number
                v-model:value="filters.qedMin"
                class="filter-control filter-control--num"
                :min="0"
                :max="1"
                :step="0.05"
                :placeholder="t('design.results.min')"
                data-testid="results-qed-min"
              />
            </div>
          </div>
        </section>

        <section class="results-workbench" data-testid="results-workbench">
          <div class="results-list" data-testid="results-list">
            <div v-if="selectedRows.length" class="results-batch" data-testid="results-batch-bar">
              <span class="results-batch__count">
                {{ t('design.results.selectedCount', { count: selectedRows.length }) }}
              </span>
              <a-button size="small" data-testid="results-export-csv" @click="exportCsv">
                {{ t('design.results.exportCsv') }}
              </a-button>
              <a-button size="small" data-testid="results-export-sdf" @click="exportSdf">
                {{ t('design.results.exportSdf') }}
              </a-button>
              <a-button size="small" type="primary" data-testid="results-save-selected" @click="openSaveModal('selected')">
                {{ t('design.results.saveSelected') }}
              </a-button>
              <a-button size="small" data-testid="results-clear-selection" @click="clearSelection">
                {{ t('design.results.clearSelection') }}
              </a-button>
            </div>

            <div class="results-list__head">
              <a-checkbox
                v-if="viewMode === 'card'"
                :checked="allPageSelected"
                :indeterminate="somePageSelected"
                data-testid="results-select-all"
                @change="toggleAll"
              >
                {{ t('design.results.selectAll') }}
              </a-checkbox>
              <span v-else />
              <div class="results-list__head-right">
                <span v-if="!selectedRows.length" class="results-list__hint">
                  {{ t('design.results.batchActions') }}
                </span>
                <a-segmented
                  v-model:value="viewMode"
                  :options="viewModeOptions"
                  size="small"
                  data-testid="results-view-toggle"
                />
              </div>
            </div>

            <div v-if="viewMode === 'table'" class="results-table-wrap">
              <table
                class="results-table"
                :class="{ 'results-table--has-metrics': numericColumns.length > 0 }"
                data-testid="molecule-table"
              >
                <thead>
                  <tr>
                    <th class="col-select">
                      <a-checkbox
                        :checked="allPageSelected"
                        :indeterminate="somePageSelected"
                        :aria-label="t('design.results.selectAll')"
                        data-testid="results-select-all"
                        @change="toggleAll"
                      />
                    </th>
                    <th class="col-index">#</th>
                    <th class="col-structure">{{ t('design.results.structureColumn') }}</th>
                    <th class="col-smiles">{{ t('design.results.smilesColumn') }}</th>
                    <th v-for="column in numericColumns" :key="column.key" class="col-num">
                      {{ column.title }}
                    </th>
                    <th v-if="hasAnyDruglikenessData" class="col-druglikeness">
                      {{ t('design.results.druglikenessColumn') }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in pagedRows"
                    :key="row.__rowKey"
                    class="results-table__row"
                    :class="{ 'is-active': row.__rowKey === activeRowKey }"
                    data-testid="molecule-row"
                    @click="setActive(row)"
                  >
                    <td class="col-select" @click.stop>
                      <a-checkbox :checked="isRowSelected(row)" @change="toggleRow(row, $event)" />
                    </td>
                    <td class="col-index">{{ rowIndex(row) }}</td>
                    <td class="col-structure">
                      <Smiles2DCell
                        v-if="rowSmiles(row)"
                        :smiles="rowSmiles(row)"
                        :width="numericColumns.length ? 84 : 104"
                        :height="numericColumns.length ? 52 : 64"
                      />
                      <span v-else class="results-table__sequence">{{ rowSequence(row) || '-' }}</span>
                    </td>
                    <td class="col-smiles">
                      <div class="results-table__smiles">
                        <code
                          class="results-table__smiles-text"
                          :title="rowSmiles(row) || rowSequence(row)"
                        >{{ rowSmiles(row) || rowSequence(row) || '-' }}</code>
                        <a-button
                          v-if="rowSmiles(row) || rowSequence(row)"
                          type="text"
                          size="small"
                          class="results-table__copy"
                          :aria-label="t('design.results.copy')"
                          data-testid="molecule-row-copy"
                          @click.stop="copyText(rowSmiles(row) || rowSequence(row))"
                        >
                          <CopyOutlined />
                        </a-button>
                      </div>
                    </td>
                    <td v-for="column in numericColumns" :key="column.key" class="col-num">
                      {{ formatMetric(row[column.key]) }}
                    </td>
                    <td v-if="hasAnyDruglikenessData" class="col-druglikeness">
                      <a-rate
                        v-if="starsForRow(row) !== null"
                        :value="starsForRow(row) ?? 0"
                        disabled
                        class="results-table__rating"
                        data-testid="molecule-row-rating"
                      />
                      <span v-else class="results-table__na">-</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-else class="molecule-grid" data-testid="molecule-grid">
              <article
                v-for="row in pagedRows"
                :key="row.__rowKey"
                class="molecule-card"
                :class="{ 'molecule-card--active': row.__rowKey === activeRowKey }"
                data-testid="molecule-card"
                @click="setActive(row)"
              >
                <header class="molecule-card__head">
                  <span class="molecule-card__select" @click.stop>
                    <a-checkbox :checked="isRowSelected(row)" @change="toggleRow(row, $event)" />
                  </span>
                  <span class="molecule-card__index">
                    {{ t('design.results.moleculeIndex', { index: rowIndex(row) }) }}
                  </span>
                  <a-rate
                    v-if="starsForRow(row) !== null"
                    :value="starsForRow(row) ?? 0"
                    disabled
                    class="molecule-card__rating"
                    data-testid="molecule-card-rating"
                  />
                </header>

                <div class="molecule-card__structure">
                  <Smiles2DCell v-if="rowSmiles(row)" :smiles="rowSmiles(row)" :width="200" :height="140" />
                  <div v-else class="molecule-card__sequence">{{ rowSequence(row) || '-' }}</div>
                </div>

                <dl v-if="rowMetrics(row).length" class="molecule-card__metrics">
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
          </div>

          <aside class="results-viewer" data-testid="results-viewer">
            <template v-if="activeRow">
              <div class="results-viewer__head">
                <h3 class="results-viewer__title">
                  {{ t('design.results.moleculeIndex', { index: rowIndex(activeRow) }) }}
                </h3>
                <label v-if="has3d" class="results-viewer__toggle">
                  <a-switch v-model:checked="simplifiedMode" size="small" data-testid="results-simplified-toggle" />
                  <span>{{ t('design.results.simplifiedMode') }}</span>
                </label>
              </div>

              <div class="results-viewer__smiles" data-testid="viewer-smiles">
                <code :title="activeSmiles">{{ activeSmiles || '-' }}</code>
                <a-button
                  v-if="activeSmiles"
                  type="text"
                  size="small"
                  :aria-label="t('design.results.copy')"
                  data-testid="viewer-smiles-copy"
                  @click="copyText(activeSmiles)"
                >
                  <CopyOutlined />
                </a-button>
              </div>

              <div v-if="has3d && !simplifiedMode" class="results-viewer__stage" data-testid="results-3d-viewer">
                <MoleculeViewer
                  v-if="viewerScene"
                  :scene="viewerScene"
                  variant="compact"
                  mode="docking"
                  :allow-native-fullscreen="false"
                />
              </div>

              <div v-else class="results-viewer__fallback" data-testid="results-viewer-fallback">
                <p v-if="!has3d" class="results-viewer__note">
                  {{ t('design.results.no3dStructure') }}
                </p>
                <p v-else class="results-viewer__note">
                  {{ t('design.results.simplifiedHint') }}
                </p>

                <div class="results-viewer__structure">
                  <Smiles2DCell
                    v-if="rowSmiles(activeRow)"
                    :smiles="rowSmiles(activeRow)"
                    block
                  />
                  <div v-else class="molecule-card__sequence">{{ rowSequence(activeRow) || '-' }}</div>
                </div>
              </div>

              <div class="results-viewer__details">
                <template v-if="rowMetrics(activeRow).length">
                  <h4 class="results-viewer__subtitle">{{ t('design.results.metricsTitle') }}</h4>
                  <dl class="results-viewer__metrics">
                    <div v-for="metric in rowMetrics(activeRow)" :key="metric.key" class="results-viewer__metric">
                      <dt>{{ metric.label }}</dt>
                      <dd>{{ metric.value }}</dd>
                    </div>
                  </dl>
                </template>

                <template v-if="activeHasLipinskiData">
                  <a-rate
                    :value="starsForRow(activeRow) ?? 0"
                    disabled
                    class="results-viewer__rating"
                    data-testid="results-viewer-rating"
                  />

                  <h4 class="results-viewer__subtitle">{{ t('design.results.lipinskiTitle') }}</h4>
                  <ul class="lipinski-list" data-testid="results-lipinski-breakdown">
                    <li
                      v-for="rule in activeRules"
                      :key="rule.id"
                      class="lipinski-list__item"
                      :class="{ 'is-violated': rule.passed === false }"
                    >
                      <span class="lipinski-list__name">{{ lipinskiLabel(rule.id) }}</span>
                      <span class="lipinski-list__value">
                        {{ rule.value === null ? '-' : formatMetric(String(rule.value)) }} / {{ rule.limit }}
                      </span>
                      <a-tag :color="lipinskiTagColor(rule.passed)">
                        {{ lipinskiStatus(rule.passed) }}
                      </a-tag>
                    </li>
                  </ul>

                  <div class="results-viewer__radar">
                    <DruglikenessRadar :properties="activeProperties" :size="240" />
                  </div>
                </template>

                <a-alert
                  v-else
                  type="info"
                  show-icon
                  class="results-viewer__guidance"
                  :message="t('design.results.noPropertyData.title')"
                  :description="t('design.results.noPropertyData.description')"
                  data-testid="results-property-guidance"
                >
                  <template #action>
                    <a-button
                      type="primary"
                      size="small"
                      data-testid="results-goto-predict"
                      @click="gotoPropertyPredict"
                    >
                      {{ t('design.results.noPropertyData.cta') }}
                    </a-button>
                  </template>
                </a-alert>
              </div>
            </template>

            <div v-else class="results-viewer__empty">{{ t('design.results.viewerEmpty') }}</div>
          </aside>
        </section>
      </template>
    </template>

    <a-modal
      v-model:open="saveModalOpen"
      :title="t('design.results.saveToSet')"
      :confirm-loading="saving"
      :ok-button-props="{ disabled: !rowsToSave.length }"
      data-testid="results-save-modal"
      @ok="handleSave"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('design.results.setName')">
          <a-input v-model:value="setName" data-testid="results-set-name" />
        </a-form-item>
        <p class="save-hint">
          {{ t(saveMode === 'selected' ? 'design.results.saveSelectedHint' : 'design.results.saveHint', { count: rowsToSave.length }) }}
        </p>
      </a-form>
    </a-modal>
  </main>
  <ResultDisclaimer />
</template>

<script setup lang="ts">
  import { formatNumber } from '@/domain/common/format'
  import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { CopyOutlined } from '@ant-design/icons-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import TaskContextBar from '@/components/tasks/TaskContextBar.vue'
  import Smiles2DCell from '@/components/tasks/Smiles2DCell.vue'
  import MoleculeViewer from '@/components/tasks/MoleculeViewer.vue'
  import DruglikenessRadar from '@/components/design/DruglikenessRadar.vue'
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
  import { fetchProtectedFileText, saveBlobAsFile } from '@/utils/protected-file-access'
  import { splitSdfRecords } from '@/domain/tasks/sdf-result'
  import {
    buildVisualizationResultItems,
    buildVisualizationScene,
    type VisualizationScene,
  } from '@/domain/tasks'
  import {
    druglikenessStars,
    evaluateLipinski,
    hasLipinskiData,
    type LipinskiProperties,
    type LipinskiRuleId,
  } from '@/domain/molecules/druglikeness'
  import { buildMoleculeCsv, buildSdfExportText } from '@/domain/molecules/molecule-export'
  import type { CandidateCreateInput } from '@/types/compounds'
  import type { DesignGenerationResult, DesignTableColumn, DesignTableRow } from '@/types/design'
  import type { Task, TaskStatus } from '@/types/models'
  import ResultDisclaimer from '@/components/common/ResultDisclaimer.vue'

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

  const taskDetail = ref<Task | null>(null)

  const filters = reactive<{
    scoreMin: number | null
    scoreMax: number | null
    mwMin: number | null
    mwMax: number | null
    logpMin: number | null
    logpMax: number | null
    hbdMin: number | null
    hbdMax: number | null
    hbaMin: number | null
    hbaMax: number | null
    qedMin: number | null
  }>({
    scoreMin: null,
    scoreMax: null,
    mwMin: null,
    mwMax: null,
    logpMin: null,
    logpMax: null,
    hbdMin: null,
    hbdMax: null,
    hbaMin: null,
    hbaMax: null,
    qedMin: null,
  })

  const sortKey = ref('')
  const sortOrder = ref<'asc' | 'desc'>('desc')
  const currentPage = ref(1)
  const pageSize = 24
  const search = ref('')
  const viewMode = ref<'table' | 'card'>('table')
  const viewModeOptions = computed(() => [
    { label: t('design.results.viewTable'), value: 'table' },
    { label: t('design.results.viewCard'), value: 'card' },
  ])

  const activeRowKey = ref<string | null>(null)
  const selectedKeys = ref<string[]>([])
  const simplifiedMode = ref(false)

  const saveModalOpen = ref(false)
  const saving = ref(false)
  const setName = ref('')
  const saveMode = ref<'all' | 'selected'>('all')

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
  const hbdColumn = computed(() => findColumn([/^hbd$/i, /h_bond_donor/i, /氢键供体/i]))
  const hbaColumn = computed(() => findColumn([/^hba$/i, /h_bond_acceptor/i, /氢键受体/i]))
  const tpsaColumn = computed(() => findColumn([/tpsa/i, /极性表面积/i]))
  const smilesColumn = computed(() => findColumn([/smiles/i]))
  const sequenceColumn = computed(() => findColumn([/sequence/i, /序列/i]))
  const isPeptideResult = computed(() => Boolean(sequenceColumn.value) && !smilesColumn.value)

  const numericColumns = computed(() => columns.value.filter((column) => column.numeric))
  const hasRangeFilters = computed(() =>
    Boolean(mwColumn.value || logpColumn.value || hbdColumn.value || hbaColumn.value || qedColumn.value)
  )

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

  function numericBounds(
    column: DesignTableColumn | undefined,
    fallbackMin: number,
    fallbackMax: number,
    step = 1
  ): { min: number; max: number; step: number } {
    if (!column) return { min: fallbackMin, max: fallbackMax, step }
    const values = rows.value
      .map(row => numericValue(row, column.key))
      .filter((value): value is number => value !== null)
    if (!values.length) return { min: fallbackMin, max: fallbackMax, step }
    const min = Math.floor(Math.min(...values))
    const max = Math.ceil(Math.max(...values))
    if (min === max) return { min: min - 1, max: max + 1, step }
    return { min, max, step }
  }

  const mwBounds = computed(() => numericBounds(mwColumn.value, 0, 1000, 1))
  const logpBounds = computed(() => numericBounds(logpColumn.value, -5, 10, 0.1))
  const hbdBounds = computed(() => numericBounds(hbdColumn.value, 0, 20, 1))
  const hbaBounds = computed(() => numericBounds(hbaColumn.value, 0, 30, 1))

  function rangeModel(
    minKey: 'mwMin' | 'logpMin' | 'hbdMin' | 'hbaMin',
    maxKey: 'mwMax' | 'logpMax' | 'hbdMax' | 'hbaMax',
    bounds: { value: { min: number; max: number; step: number } }
  ) {
    return computed<number[]>({
      get: () => [
        filters[minKey] ?? bounds.value.min,
        filters[maxKey] ?? bounds.value.max,
      ],
      set: (value: number[]) => {
        const min = value[0] ?? bounds.value.min
        const max = value[1] ?? bounds.value.max
        filters[minKey] = min <= bounds.value.min ? null : min
        filters[maxKey] = max >= bounds.value.max ? null : max
      },
    })
  }

  const mwRange = rangeModel('mwMin', 'mwMax', mwBounds)
  const logpRange = rangeModel('logpMin', 'logpMax', logpBounds)
  const hbdRange = rangeModel('hbdMin', 'hbdMax', hbdBounds)
  const hbaRange = rangeModel('hbaMin', 'hbaMax', hbaBounds)

  const filteredRows = computed(() => {
    const keyword = search.value.trim().toLowerCase()
    return rows.value.filter((row) => {
      if (keyword) {
        const hit =
          rowSmiles(row).toLowerCase().includes(keyword) ||
          rowSequence(row).toLowerCase().includes(keyword)
        if (!hit) return false
      }
      const score = numericValue(row, scoreColumn.value?.key)
      const mw = numericValue(row, mwColumn.value?.key)
      const logp = numericValue(row, logpColumn.value?.key)
      const hbd = numericValue(row, hbdColumn.value?.key)
      const hba = numericValue(row, hbaColumn.value?.key)
      const qed = numericValue(row, qedColumn.value?.key)
      if (filters.scoreMin !== null && (score === null || score < filters.scoreMin)) return false
      if (filters.scoreMax !== null && (score === null || score > filters.scoreMax)) return false
      if (filters.mwMin !== null && (mw === null || mw < filters.mwMin)) return false
      if (filters.mwMax !== null && (mw === null || mw > filters.mwMax)) return false
      if (filters.logpMin !== null && (logp === null || logp < filters.logpMin)) return false
      if (filters.logpMax !== null && (logp === null || logp > filters.logpMax)) return false
      if (filters.hbdMin !== null && (hbd === null || hbd < filters.hbdMin)) return false
      if (filters.hbdMax !== null && (hbd === null || hbd > filters.hbdMax)) return false
      if (filters.hbaMin !== null && (hba === null || hba < filters.hbaMin)) return false
      if (filters.hbaMax !== null && (hba === null || hba > filters.hbaMax)) return false
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

  const selectedRows = computed(() =>
    sortedRows.value.filter(row => selectedKeys.value.includes(row.__rowKey))
  )

  const rowsToSave = computed(() =>
    saveMode.value === 'selected' ? selectedRows.value : saveableRows.value
  )

  const canSave = computed(
    () => isTerminal.value && !isFailure.value && saveableRows.value.length > 0
  )

  const activeRow = computed(
    () => sortedRows.value.find(row => row.__rowKey === activeRowKey.value) ?? null
  )

  const viewerScene = computed<VisualizationScene | null>(() =>
    taskDetail.value ? buildVisualizationScene(taskDetail.value) : null
  )
  const has3d = computed(() => Boolean(viewerScene.value?.entries.length))

  const activeProperties = computed<LipinskiProperties | null>(() =>
    activeRow.value ? propertiesForRow(activeRow.value) : null
  )
  const activeRules = computed(() => evaluateLipinski(activeProperties.value))
  const activeHasLipinskiData = computed(() => hasLipinskiData(activeProperties.value))
  const activeSmiles = computed(() => {
    if (!activeRow.value) return ''
    return rowSmiles(activeRow.value) || rowSequence(activeRow.value)
  })

  /** 只有整张表里真的存在理化性质时才展示类药性列/星级，避免一排空灰星。 */
  const hasAnyDruglikenessData = computed(() =>
    rows.value.some(row => hasLipinskiData(propertiesForRow(row)))
  )

  const pageKeys = computed(() => pagedRows.value.map(row => row.__rowKey))
  const allPageSelected = computed(
    () => pageKeys.value.length > 0 && pageKeys.value.every(key => selectedKeys.value.includes(key))
  )
  const somePageSelected = computed(
    () => pageKeys.value.some(key => selectedKeys.value.includes(key)) && !allPageSelected.value
  )

  watch(
    [filteredRows, sortKey, sortOrder],
    () => {
      currentPage.value = 1
    }
  )

  watch(
    sortedRows,
    nextRows => {
      if (!nextRows.length) {
        activeRowKey.value = null
        return
      }
      if (!nextRows.some(row => row.__rowKey === activeRowKey.value)) {
        activeRowKey.value = nextRows[0]?.__rowKey ?? null
      }
    },
    { immediate: true }
  )

  function rowSmiles(row: DesignTableRow): string {
    return smilesColumn.value ? (row[smilesColumn.value.key] ?? '').trim() : ''
  }

  function rowSequence(row: DesignTableRow): string {
    return sequenceColumn.value ? (row[sequenceColumn.value.key] ?? '').trim() : ''
  }

  function rowIndex(row: DesignTableRow): number {
    const numeric = Number(row.__rowKey)
    return Number.isFinite(numeric) ? numeric + 1 : pagedRows.value.indexOf(row) + 1
  }

  function propertiesForRow(row: DesignTableRow): LipinskiProperties {
    return {
      mw: numericValue(row, mwColumn.value?.key),
      logp: numericValue(row, logpColumn.value?.key),
      hbd: numericValue(row, hbdColumn.value?.key),
      hba: numericValue(row, hbaColumn.value?.key),
      tpsa: numericValue(row, tpsaColumn.value?.key),
      qed: numericValue(row, qedColumn.value?.key),
    }
  }

  function starsForRow(row: DesignTableRow): number | null {
    return druglikenessStars(propertiesForRow(row))
  }

  function lipinskiLabel(id: LipinskiRuleId): string {
    switch (id) {
      case 'mw':
        return t('design.results.druglikeness.rules.mw')
      case 'logp':
        return t('design.results.druglikeness.rules.logp')
      case 'hbd':
        return t('design.results.druglikeness.rules.hbd')
      case 'hba':
        return t('design.results.druglikeness.rules.hba')
      case 'tpsa':
        return t('design.results.druglikeness.rules.tpsa')
    }
  }

  /** 缺值（passed === null）必须中性展示，绝不能算「符合」。 */
  function lipinskiTagColor(passed: boolean | null): string {
    if (passed === null) return 'default'
    return passed ? 'success' : 'error'
  }

  function lipinskiStatus(passed: boolean | null): string {
    if (passed === null) return t('design.results.lipinskiUnknown')
    return passed ? t('design.results.lipinskiPass') : t('design.results.lipinskiFail')
  }

  async function copyText(text: string): Promise<void> {
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      message.success(t('common.copySuccess'))
    } catch {
      message.warning(t('design.results.copyFailed'))
    }
  }

  function gotoPropertyPredict(): void {
    const projectId = detail.value?.project_id
    void router.push({
      name: 'PropertyPredict',
      query: projectId ? { project_id: projectId } : undefined,
    })
  }

  function formatMetric(raw: string | undefined): string {
    const value = Number((raw ?? '').trim())
    if (!Number.isFinite(value)) {
      return raw && raw.trim() !== '' ? raw : '-'
    }
    return formatNumber(value, 3)
  }

  function rowMetrics(row: DesignTableRow): Array<{ key: string; label: string; value: string }> {
    // 直接遍历 CSV 实际列：只输出结构/序列之外的所有属性，CSV 里多出来的列也能展示。
    return columns.value
      .filter(
        column => column.key !== smilesColumn.value?.key && column.key !== sequenceColumn.value?.key
      )
      .map(column => ({
        key: column.key,
        label: column.title,
        value: formatMetric(row[column.key]),
      }))
  }

  function resetFilters(): void {
    search.value = ''
    filters.scoreMin = null
    filters.scoreMax = null
    filters.mwMin = null
    filters.mwMax = null
    filters.logpMin = null
    filters.logpMax = null
    filters.hbdMin = null
    filters.hbdMax = null
    filters.hbaMin = null
    filters.hbaMax = null
    filters.qedMin = null
  }

  function initializeSort(): void {
    if (sortKey.value) {
      return
    }
    sortKey.value = scoreColumn.value?.key ?? numericColumns.value[0]?.key ?? ''
  }

  function setActive(row: DesignTableRow): void {
    activeRowKey.value = row.__rowKey
  }

  function isRowSelected(row: DesignTableRow): boolean {
    return selectedKeys.value.includes(row.__rowKey)
  }

  function toggleRow(row: DesignTableRow, event: Event): void {
    const checked = event.target instanceof HTMLInputElement
      ? event.target.checked
      : !isRowSelected(row)
    if (checked) {
      if (!isRowSelected(row)) selectedKeys.value = [...selectedKeys.value, row.__rowKey]
    } else {
      selectedKeys.value = selectedKeys.value.filter(key => key !== row.__rowKey)
    }
  }

  function toggleAll(event: Event): void {
    const checked = event.target instanceof HTMLInputElement
      ? event.target.checked
      : !allPageSelected.value
    if (checked) {
      selectedKeys.value = Array.from(new Set([...selectedKeys.value, ...pageKeys.value]))
    } else {
      const keys = new Set(pageKeys.value)
      selectedKeys.value = selectedKeys.value.filter(key => !keys.has(key))
    }
  }

  function clearSelection(): void {
    selectedKeys.value = []
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
        await Promise.all([loadTable(result), loadViewerTask()])
      }
    } catch {
      // 结果尚未生成时后端可能返回 404，转为追踪任务状态。
      startTracking()
    }
  }

  async function loadViewerTask(): Promise<void> {
    try {
      const response = await getTaskDetail(taskId.value)
      taskDetail.value = response.data
    } catch {
      taskDetail.value = null
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

  function openSaveModal(mode: 'all' | 'selected'): void {
    saveMode.value = mode
    setName.value = t('design.results.defaultSetName', {
      id: taskId.value.slice(0, 8),
    })
    saveModalOpen.value = true
  }

  function exportTargetRows(): DesignTableRow[] {
    return selectedRows.value.length ? selectedRows.value : saveableRows.value
  }

  async function exportCsv(): Promise<void> {
    const targetRows = exportTargetRows()
    if (!targetRows.length) {
      message.warning(t('design.results.exportEmpty'))
      return
    }
    const csv = buildMoleculeCsv(columns.value, targetRows)
    await saveBlobAsFile(csv, `molecules-${taskId.value.slice(0, 8)}.csv`, 'text/csv;charset=utf-8')
    message.success(t('design.results.exportCsvSuccess', { count: targetRows.length }))
  }

  async function findSdfText(): Promise<string> {
    if (!taskDetail.value) return ''
    // 同时覆盖 output_files 与标准产物（ligand_structure / molecule_table 的 3D SDF）。
    const items = buildVisualizationResultItems(taskDetail.value)
    const entry = items.find(item => item.kind === 'structure' && item.entry?.format === 'sdf')?.entry
    if (!entry) return ''
    try {
      return await fetchProtectedFileText(entry.url)
    } catch {
      return ''
    }
  }

  async function exportSdf(): Promise<void> {
    const targetRows = exportTargetRows()
    if (!targetRows.length) {
      message.warning(t('design.results.exportEmpty'))
      return
    }
    const sdfText = await findSdfText()
    const text = buildSdfExportText(
      sdfText ? splitSdfRecords(sdfText) : [],
      targetRows.map(row => ({ smiles: rowSmiles(row) }))
    )
    await saveBlobAsFile(text, `molecules-${taskId.value.slice(0, 8)}.sdf`, 'chemical/x-mdl-sdfile')
    message.success(t('design.results.exportSdfSuccess', { count: targetRows.length }))
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
    if (!rowsToSave.value.length) {
      message.warning(t('design.results.nothingToSave'))
      return
    }

    saving.value = true
    try {
      const candidateIds = await Promise.all(
        rowsToSave.value.map(async (row) => {
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
    max-width: @page-max-width;
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
  .results-filters__sliders {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }

  .results-filters__search {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .results-filters__search-input {
    max-width: 420px;
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

  .filter-slider {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 230px;
    flex: 1 1 240px;
  }

  .filter-slider__control {
    flex: 1 1 110px;
    min-width: 100px;
  }

  .filter-slider__readout {
    color: @text-tertiary;
    font-size: @font-size-xs;
    white-space: nowrap;
  }

  .filter-slider--inline {
    flex: 0 1 220px;
    min-width: 180px;
  }

  /* 桌面端约 45% 列表 / 55% 黏性详情面板；窄屏自动堆叠。 */
  .results-workbench {
    display: grid;
    grid-template-columns: minmax(0, 9fr) minmax(0, 11fr);
    gap: 20px;
    align-items: start;
  }

  .results-list {
    min-width: 0;
  }

  .results-list__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
  }

  .results-list__head-right {
    display: inline-flex;
    align-items: center;
    gap: 12px;
  }

  .results-list__hint {
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  /* 高密度表格：一屏尽可能多地扫分子，只有右侧详情才放重组件。 */
  .results-table-wrap {
    overflow-x: auto;
    border: 1px solid @border-color;
    border-radius: 8px;
    background: @bg-surface;
  }

  .results-table {
    width: 100%;
    border-collapse: collapse;
    font-size: @font-size-sm;
  }

  .results-table th,
  .results-table td {
    padding: 6px 8px;
    border-bottom: 1px solid @border-color;
    text-align: left;
    vertical-align: middle;
  }

  .results-table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: @surface-sunken;
    color: @text-secondary;
    font-weight: @font-weight-medium;
    white-space: nowrap;
  }

  .results-table tbody tr {
    cursor: pointer;
  }

  .results-table tbody tr:hover {
    background: @bg-hover;
  }

  .results-table tbody tr.is-active {
    background: @accent-color-light;
    box-shadow: inset 2px 0 0 @primary-color;
  }

  .results-table tbody tr:last-child td {
    border-bottom: 0;
  }

  .results-table .col-select {
    width: 36px;
  }

  .results-table .col-index {
    width: 48px;
    color: @text-tertiary;
  }

  .results-table .col-num {
    text-align: right;
    white-space: nowrap;
  }

  .results-table .col-structure {
    width: 112px;
  }

  .results-table .col-structure :deep(.smiles-cell) {
    width: 104px;
    min-width: 104px;
    height: 64px;
  }

  .results-table .col-smiles {
    min-width: 140px;
    max-width: 320px;
  }

  /* 有数值列时收紧结构与 SMILES 列宽，让关键数值列直接在左栏可视区内呈现 */
  .results-table--has-metrics .col-structure {
    width: 92px;
  }

  .results-table--has-metrics .col-structure :deep(.smiles-cell) {
    width: 84px;
    min-width: 84px;
    height: 52px;
  }

  .results-table--has-metrics .col-smiles {
    width: 128px;
    min-width: 112px;
    max-width: 136px;
  }

  .results-table .col-druglikeness {
    width: 104px;
  }

  .results-table__smiles {
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
  }

  .results-table__smiles-text {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: @text-primary;
    font-family: @font-family-mono;
    font-size: 12px;
  }

  .results-table__copy {
    flex: 0 0 auto;
  }

  .results-table__sequence {
    display: inline-block;
    max-width: 104px;
    overflow-wrap: anywhere;
    color: @text-secondary;
    font-family: @font-family-mono;
    font-size: 11px;
  }

  .results-table__rating {
    font-size: 12px;
    line-height: 1;
  }

  .results-table__na {
    color: @text-tertiary;
  }

  .results-batch {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
    padding: 10px 12px;
    border: 1px solid @accent-color-border;
    border-radius: 8px;
    background: @accent-color-light;
  }

  .results-batch__count {
    margin-right: auto;
    color: @text-secondary;
    font-size: @font-size-sm;
    font-weight: @font-weight-medium;
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
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
    cursor: pointer;
  }

  .molecule-card:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  }

  .molecule-card--active {
    border-color: @primary-color;
    box-shadow: 0 0 0 1px @primary-color;
  }

  .molecule-card__head {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px 0;
  }

  .molecule-card__index {
    color: @text-secondary;
    font-size: @font-size-xs;
    font-weight: @font-weight-medium;
  }

  .molecule-card__rating {
    margin-left: auto;
    font-size: 12px;
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
    padding: 12px 16px 8px;
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

  .results-viewer {
    position: sticky;
    top: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
    padding: 16px;
    border: 1px solid @border-color;
    border-radius: 8px;
    background: @bg-surface;
  }

  .results-viewer__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .results-viewer__title {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }

  .results-viewer__toggle {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: @text-secondary;
    font-size: @font-size-xs;
    cursor: pointer;
  }

  .results-viewer__smiles {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 10px;
    border: 1px solid @border-color;
    border-radius: 6px;
    background: @surface-sunken;
  }

  .results-viewer__smiles code {
    flex: 1 1 auto;
    min-width: 0;
    color: @text-primary;
    font-family: @font-family-mono;
    font-size: 12px;
    overflow-wrap: anywhere;
  }

  .results-viewer__rating {
    font-size: 14px;
  }

  .results-viewer__guidance {
    margin: 0;
  }

  .results-viewer__stage {
    height: 480px;
    overflow: hidden;
    border-radius: 8px;
  }

  .results-viewer__fallback,
  .results-viewer__details {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .results-viewer__note {
    margin: 0;
    color: @text-tertiary;
    font-size: @font-size-sm;
    line-height: 1.5;
  }

  .results-viewer__structure {
    width: 100%;
  }

  .results-viewer__subtitle {
    margin: 4px 0 0;
    font-size: 14px;
    font-weight: 600;
  }

  .results-viewer__metrics {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 10px;
    margin: 0;
  }

  .results-viewer__metric dt {
    color: @text-tertiary;
    font-size: 12px;
  }

  .results-viewer__metric dd {
    margin: 2px 0 0;
    font-weight: 600;
  }

  .lipinski-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .lipinski-list__item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border-radius: 6px;
    background: @surface-sunken;
    font-size: @font-size-sm;
  }

  .lipinski-list__item.is-violated {
    background: rgba(239, 68, 68, 0.1);
  }

  .lipinski-list__name {
    flex: 1 1 auto;
    color: @text-secondary;
  }

  .lipinski-list__value {
    color: @text-primary;
    font-weight: 500;
  }

  .results-viewer__radar {
    display: flex;
    justify-content: center;
    padding-top: 4px;
  }

  .results-viewer__empty {
    padding: 48px 0;
    color: @text-tertiary;
    text-align: center;
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

  @media (max-width: @screen-lg) {
    .results-workbench {
      grid-template-columns: minmax(0, 1fr);
    }

    .results-viewer {
      position: static;
    }

    .results-viewer__stage {
      height: 360px;
    }
  }
</style>
