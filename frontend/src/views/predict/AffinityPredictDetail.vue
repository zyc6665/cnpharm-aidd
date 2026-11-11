<template>
  <div v-if="comparison.current" class="affinity-detail" data-testid="affinity-detail">
    <section class="affinity-hero">
      <div class="affinity-hero__identity">
        <span class="affinity-eyebrow">{{ t('predict.result.detailSectionAffinityIdentity') }}</span>
        <h2 class="affinity-hero__title">{{ comparison.current.moleculeId }}</h2>
        <div class="affinity-hero__meta">
          <span>{{ t('predict.result.detailFieldComplexId') }} {{ complexId || '-' }}</span>
          <span v-if="duration !== null">{{ t('predict.result.detailFieldDuration') }} {{ formatNumber(duration) }} s</span>
        </div>
        <div class="affinity-hero__report">
          <span>{{ t('predict.result.detailTool') }} {{ toolName || '-' }}</span>
          <span class="affinity-mono">{{ taskId }}</span>
        </div>
      </div>

      <div class="affinity-kpis">
        <article class="affinity-kpi">
          <span class="affinity-kpi__label">{{ t('predict.result.affinityRankLabel') }}</span>
          <div class="affinity-kpi__value-row">
            <strong class="affinity-kpi__value" data-testid="affinity-rank-value">#{{ comparison.rank }}</strong>
            <span class="affinity-kpi__muted">/ {{ comparison.total }}</span>
          </div>
          <span class="affinity-kpi__hint">{{ t('predict.result.affinityRankHint') }}</span>
        </article>

        <article class="affinity-kpi affinity-kpi--score">
          <span class="affinity-kpi__label">{{ t('predict.result.detailFieldPredictedAffinity') }}</span>
          <strong class="affinity-kpi__value affinity-kpi__value--score" data-testid="affinity-score-value">
            {{ formatNumber(comparison.current.affinity) }}
          </strong>
          <a-tag class="affinity-quality" :color="qualityColor" data-testid="affinity-quality-tag">
            {{ t(qualityLabelKey) }}
          </a-tag>
        </article>

        <article class="affinity-kpi">
          <span class="affinity-kpi__label">{{ t('predict.result.affinityDeltaMedian') }}</span>
          <strong class="affinity-kpi__value" :class="deltaClass" data-testid="affinity-delta-value">
            {{ signedDelta }}
          </strong>
          <span class="affinity-kpi__hint">
            {{ t('predict.result.affinityMedianValue', { value: formatNumber(comparison.median) }) }}
          </span>
        </article>
      </div>
    </section>

    <a-alert
      class="affinity-summary"
      type="info"
      show-icon
      :message="summary"
      data-testid="affinity-summary"
    />

    <div class="affinity-columns">
      <section class="affinity-panel affinity-panel--comparison">
        <header class="affinity-panel__head">
          <div>
            <h3>{{ t('predict.result.affinityComparisonTitle') }}</h3>
            <p>{{ t('predict.result.affinityComparisonHint') }}</p>
          </div>
        </header>

        <a-table
          class="affinity-candidate-table"
          :columns="candidateColumns"
          :data-source="comparison.candidates"
          :pagination="false"
          :scroll="{ y: 248 }"
          row-key="rowKey"
          size="small"
          :row-class-name="candidateRowClass"
          :custom-row="candidateRow"
          data-testid="affinity-comparison-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'moleculeId'">
              <span class="affinity-candidate-name">{{ record.moleculeId }}</span>
              <a-tag v-if="record.rowKey === comparison.current?.rowKey" color="blue" class="affinity-current-tag">
                {{ t('predict.result.affinityCurrentTag') }}
              </a-tag>
            </template>
            <template v-else-if="column.key === 'affinity'">
              <div class="affinity-score-cell">
                <span>{{ formatNumber(record.affinity) }}</span>
                <span class="affinity-score-bar">
                  <i :style="{ width: `${scorePercent(record.affinity)}%` }" />
                </span>
              </div>
            </template>
            <template v-else-if="column.key === 'ligandToPocket' || column.key === 'pocketToLigand'">
              {{ formatNumber(record[column.key]) }}
            </template>
            <template v-else>{{ record[column.key] }}</template>
          </template>
        </a-table>
      </section>

      <section class="affinity-panel affinity-panel--breakdown">
        <header class="affinity-panel__head">
          <div>
            <h3>{{ t('predict.result.affinityBreakdownTitle') }}</h3>
            <p>{{ t('predict.result.affinityBreakdownHint') }}</p>
          </div>
        </header>

        <div class="affinity-direction">
          <div class="affinity-direction__row">
            <div class="affinity-direction__label">
              <span>{{ t('predict.result.detailFieldLigandToPocket') }}</span>
              <strong>{{ formatNumber(comparison.current.ligandToPocket) }}</strong>
            </div>
            <div class="affinity-bar">
              <span class="affinity-bar__fill affinity-bar__fill--ligand" :style="{ width: `${directionPercent(comparison.current.ligandToPocket)}%` }" />
            </div>
          </div>
          <div class="affinity-direction__row">
            <div class="affinity-direction__label">
              <span>{{ t('predict.result.detailFieldPocketToLigand') }}</span>
              <strong>{{ formatNumber(comparison.current.pocketToLigand) }}</strong>
            </div>
            <div class="affinity-bar">
              <span class="affinity-bar__fill affinity-bar__fill--pocket" :style="{ width: `${directionPercent(comparison.current.pocketToLigand)}%` }" />
            </div>
          </div>
        </div>

        <p v-if="comparison.scale" class="affinity-scale">
          {{ t('predict.result.detailFieldScale') }}：{{ comparison.scale }}
        </p>

        <a-collapse ghost class="affinity-technical">
          <a-collapse-panel key="technical" :header="t('predict.result.affinityTechnical')">
            <div class="affinity-tech-grid">
              <div v-for="item in technicalItems" :key="item.label" class="affinity-tech-item">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
            <dl class="affinity-report">
              <dt>{{ t('predict.result.detailTask') }}</dt>
              <dd class="affinity-mono">{{ taskId }}</dd>
              <dt>{{ t('predict.result.detailTool') }}</dt>
              <dd>{{ toolName || '-' }}</dd>
              <dt>{{ t('predict.result.detailSource') }}</dt>
              <dd>{{ t('predict.result.detailSourceValue') }}</dd>
            </dl>
          </a-collapse-panel>
        </a-collapse>
      </section>
    </div>
  </div>
  <a-empty v-else :description="t('predict.result.detailNoData')" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  buildAffinityComparison,
  readAffinityField,
  readAffinityNumber,
  type AffinityCandidate
} from './affinityComparison'
import type { CsvPreviewRow } from '@/domain/tasks/csv-result'

const props = defineProps<{
  row: CsvPreviewRow
  rows: CsvPreviewRow[]
  taskId: string
  toolName?: string | null
}>()

const emit = defineEmits<{ (event: 'selectCandidate', row: CsvPreviewRow): void }>()
const { t } = useI18n()

const comparison = computed(() => buildAffinityComparison(props.rows.length ? props.rows : [props.row], props.row))

const complexId = computed(() => readAffinityField(props.row, 'complexId'))
const duration = computed(() => readAffinityNumber(props.row, 'duration'))

const qualityLabelKey = computed(() => {
  switch (comparison.value.quality) {
    case 'single':
      return 'predict.result.affinityQualitySingle'
    case 'best':
      return 'predict.result.affinityQualityBest'
    case 'top':
      return 'predict.result.affinityQualityTop'
    case 'middle':
      return 'predict.result.affinityQualityMiddle'
    default:
      return 'predict.result.affinityQualityLow'
  }
})

const qualityColor = computed(() => {
  switch (comparison.value.quality) {
    case 'best':
    case 'top':
      return 'green'
    case 'middle':
      return 'gold'
    case 'low':
      return 'red'
    default:
      return 'default'
  }
})

const signedDelta = computed(() => {
  const delta = comparison.value.deltaToMedian
  if (delta === null) {
    return '-'
  }
  if (Math.abs(delta) < 0.0005) {
    return '0.000'
  }
  return `${delta > 0 ? '+' : ''}${formatNumber(delta)}`
})

const deltaClass = computed(() => {
  const delta = comparison.value.deltaToMedian
  if (delta === null || Math.abs(delta) < 0.0005) {
    return ''
  }
  return delta > 0 ? 'affinity-kpi__value--good' : 'affinity-kpi__value--bad'
})

const summary = computed(() => {
  const value = comparison.value
  if (!value.current) {
    return ''
  }
  if (value.total <= 1) {
    return t('predict.result.affinitySummarySingle')
  }
  if (value.rank === 1) {
    return t('predict.result.affinitySummaryBest', {
      total: value.total,
      delta: formatNumber(Math.abs(value.deltaToMedian ?? 0))
    })
  }
  const direction = (value.deltaToMedian ?? 0) >= 0
    ? t('predict.result.affinityAbove')
    : t('predict.result.affinityBelow')
  return t('predict.result.affinitySummary', {
    total: value.total,
    rank: value.rank,
    gap: formatNumber(Math.abs(value.gapToBest ?? 0)),
    direction,
    delta: formatNumber(Math.abs(value.deltaToMedian ?? 0))
  })
})

const candidateColumns = computed(() => [
  { title: '#', dataIndex: 'rank', key: 'rank', width: 50 },
  { title: t('predict.result.affinityCandidateMolecule'), dataIndex: 'moleculeId', key: 'moleculeId' },
  { title: t('predict.result.detailFieldPredictedAffinity'), dataIndex: 'affinity', key: 'affinity', width: 150 },
  { title: t('predict.result.detailFieldLigandToPocket'), dataIndex: 'ligandToPocket', key: 'ligandToPocket', width: 108, align: 'right' as const },
  { title: t('predict.result.detailFieldPocketToLigand'), dataIndex: 'pocketToLigand', key: 'pocketToLigand', width: 108, align: 'right' as const }
])

const technicalItems = computed(() => [
  { label: t('predict.result.detailFieldPocketAtoms'), value: formatNumber(readAffinityNumber(props.row, 'pocketAtoms')) },
  { label: t('predict.result.detailFieldLigandAtoms'), value: formatNumber(readAffinityNumber(props.row, 'ligandAtoms')) },
  { label: t('predict.result.detailFieldPocketBonds'), value: formatNumber(readAffinityNumber(props.row, 'pocketBonds')) },
  { label: t('predict.result.detailFieldLigandBonds'), value: formatNumber(readAffinityNumber(props.row, 'ligandBonds')) },
  { label: t('predict.result.detailFieldGeneratedPocketAtoms'), value: formatNumber(readAffinityNumber(props.row, 'generatedPocketAtoms')) }
])

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return '-'
  }
  return String(Number(value.toFixed(3)))
}

function rangeBounds(): { min: number; max: number } {
  const values = comparison.value.candidates.map(candidate => candidate.affinity)
  return {
    min: Math.min(...values),
    max: Math.max(...values)
  }
}

function scorePercent(value: number): number {
  const { min, max } = rangeBounds()
  if (max === min) {
    return 100
  }
  return 12 + ((value - min) / (max - min)) * 88
}

function directionPercent(value: number | null): number {
  if (value === null) {
    return 0
  }
  const max = Math.max(
    Math.abs(comparison.value.current?.ligandToPocket ?? 0),
    Math.abs(comparison.value.current?.pocketToLigand ?? 0),
    0.0001
  )
  return Math.min(100, Math.max(0, (Math.abs(value) / max) * 100))
}

function candidateRowClass(record: AffinityCandidate): string {
  return record.rowKey === comparison.value.current?.rowKey ? 'affinity-candidate-row--current' : ''
}

function candidateRow(record: AffinityCandidate): Record<string, unknown> {
  return {
    onClick: () => emit('selectCandidate', record.row),
    style: 'cursor: pointer;'
  }
}
</script>

<style scoped lang="less">
.affinity-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px 22px 28px;
}

.affinity-hero {
  display: grid;
  grid-template-columns: minmax(240px, 1.1fr) minmax(480px, 2fr);
  gap: 18px;
  padding: 20px 22px;
  border: 1px solid var(--ant-color-border-secondary, #e5e7eb);
  border-radius: 12px;
  background:
    radial-gradient(circle at 10% 20%, rgba(59, 130, 246, 0.12), transparent 36%),
    var(--ant-color-bg-container, #fff);
}

.affinity-hero__identity {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.affinity-eyebrow,
.affinity-kpi__label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ant-color-text-tertiary, #8c8c8c);
}

.affinity-hero__title {
  margin: 0;
  font-size: 28px;
  line-height: 1.1;
  font-weight: 700;
  color: var(--ant-color-text, #111827);
}

.affinity-hero__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  font-size: 13px;
  color: var(--ant-color-text-secondary, #595959);
}

.affinity-hero__report {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--ant-color-text-tertiary, #8c8c8c);
}

.affinity-mono {
  font-family: 'SFMono-Regular', Consolas, monospace;
  word-break: break-all;
}

.affinity-kpis {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.affinity-kpi {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 112px;
  padding: 14px 16px;
  border: 1px solid var(--ant-color-border-secondary, #e5e7eb);
  border-radius: 10px;
  background: var(--ant-color-bg-container, #fff);
}

.affinity-kpi--score {
  border-color: rgba(59, 130, 246, 0.42);
  box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.08);
}

.affinity-kpi__value-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.affinity-kpi__value {
  font-size: 30px;
  line-height: 1.05;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--ant-color-text, #111827);
}

.affinity-kpi__value--score {
  color: #3b82f6;
}

.affinity-kpi__value--good {
  color: #18a058;
}

.affinity-kpi__value--bad {
  color: #e5484d;
}

.affinity-kpi__muted,
.affinity-kpi__hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary, #8c8c8c);
}

.affinity-quality {
  align-self: flex-start;
  margin-top: 2px;
}

.affinity-summary {
  margin: 0;
}

.affinity-columns {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(320px, 1fr);
  gap: 16px;
  align-items: start;
}

.affinity-panel {
  min-width: 0;
  padding: 16px 18px;
  border: 1px solid var(--ant-color-border-secondary, #e5e7eb);
  border-radius: 12px;
  background: var(--ant-color-bg-container, #fff);
}

.affinity-panel__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.affinity-panel__head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--ant-color-text, #111827);
}

.affinity-panel__head p {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ant-color-text-tertiary, #8c8c8c);
}

.affinity-candidate-name {
  font-weight: 600;
}

.affinity-current-tag {
  margin-left: 8px;
}

.affinity-score-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.affinity-score-bar {
  flex: 1;
  height: 5px;
  min-width: 32px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--ant-color-fill-secondary, #f0f0f0);
}

.affinity-score-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #3b82f6;
}

.affinity-candidate-table :deep(.affinity-candidate-row--current) > td {
  background: rgba(59, 130, 246, 0.09);
}

.affinity-direction {
  display: flex;
  flex-direction: column;
  gap: 18px;
  margin: 18px 0 12px;
}

.affinity-direction__row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.affinity-direction__label {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-size: 12px;
  color: var(--ant-color-text-secondary, #595959);
}

.affinity-direction__label strong {
  font-size: 18px;
  font-variant-numeric: tabular-nums;
  color: var(--ant-color-text, #111827);
}

.affinity-bar {
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--ant-color-fill-secondary, #f0f0f0);
}

.affinity-bar__fill {
  display: block;
  height: 100%;
  min-width: 4px;
  border-radius: inherit;
}

.affinity-bar__fill--ligand {
  background: #3b82f6;
}

.affinity-bar__fill--pocket {
  background: #8b5cf6;
}

.affinity-scale {
  margin: 8px 0 0;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ant-color-text-secondary, #595959);
  background: var(--ant-color-fill-quaternary, #fafafa);
}

.affinity-technical {
  margin-top: 12px;
}

.affinity-tech-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}

.affinity-tech-item {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary, #fafafa);
  font-size: 12px;
}

.affinity-tech-item span {
  color: var(--ant-color-text-secondary, #595959);
}

.affinity-tech-item strong {
  font-variant-numeric: tabular-nums;
}

.affinity-report {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  margin: 0;
  font-size: 12px;
}

.affinity-report dt,
.affinity-report dd {
  margin: 0;
  padding: 6px 0;
  border-top: 1px solid var(--ant-color-border-secondary, #f0f0f0);
}

.affinity-report dt {
  color: var(--ant-color-text-tertiary, #8c8c8c);
}

.affinity-report dd {
  color: var(--ant-color-text, #111827);
  word-break: break-all;
}

@media (max-width: 1100px) {
  .affinity-hero,
  .affinity-columns {
    grid-template-columns: minmax(0, 1fr);
  }

  .affinity-kpis {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .affinity-kpis {
    grid-template-columns: minmax(0, 1fr);
  }

  .affinity-tech-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
