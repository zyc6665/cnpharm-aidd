---
name: molecule-predict-detail
description: 单分子预测结果详情抽屉，按模型能力族（ADMET / 亲和力 / 通用）选择字段与分组；同族不同模型复用，新模型无需单独建页面。
---

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts'
import Smiles2DCell from '@/components/tasks/Smiles2DCell.vue'
import { downloadCsv } from '@/views/predict/csv-export'
import AffinityPredictDetail from './AffinityPredictDetail.vue'
import { chartColors } from '@/utils/chartTheme'
import {
  resolvePredictDetailProfile,
  type PredictDetailMetricDef,
  type PredictDetailPolarity,
  type PredictDetailProfile
} from '@/views/predict/predictDetailProfiles'
import type { CsvPreviewColumn, CsvPreviewRow } from '@/domain/tasks/csv-result'
import ResultDisclaimer from '@/components/common/ResultDisclaimer.vue'

const props = defineProps<{
  row: CsvPreviewRow | null
  columns: CsvPreviewColumn[]
  taskId: string
  /** 当前结果表全部行，用于同批候选对比。 */
  rows?: CsvPreviewRow[]
  /** 模型能力族（后端 model_family；缺失时上层按 slug 兜底）。 */
  family?: string | null
  /** 任务使用的模型/工具名，用于报告信息，不再硬编码某个模型。 */
  toolName?: string | null
}>()

const emit = defineEmits<{ (event: 'selectCandidate', row: CsvPreviewRow): void }>()

const open = defineModel<boolean>('open', { default: false })
const { t } = useI18n()

const view = ref<'table' | 'radar'>('table')
const detailRef = ref<HTMLDivElement | null>(null)
const radarRef = ref<HTMLDivElement | null>(null)
const isDark = ref(false)
let radarChart: echarts.ECharts | null = null
let themeObserver: MutationObserver | null = null

function readTheme(): boolean {
  if (typeof document === 'undefined') {
    return false
  }
  return document.documentElement.getAttribute('data-theme') === 'dark'
}

const profile = computed<PredictDetailProfile>(() => resolvePredictDetailProfile(props.family))

function normalize(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, '')
}

const columnIndex = computed(() => {
  const map = new Map<string, CsvPreviewColumn>()
  for (const column of props.columns) {
    map.set(normalize(column.key), column)
    if (column.originalKey) {
      map.set(normalize(column.originalKey), column)
    }
  }
  return map
})

const smiles = computed(() => {
  if (!props.row) {
    return ''
  }
  const column = columnIndex.value.get('smiles')
  return column ? String(props.row[column.key] ?? '').trim() : ''
})

interface BasicItem {
  label: string
  value: string
  unit?: string
}

interface SectionMetric {
  label: string
  raw: string
  value: string
  unit?: string
  status: 'good' | 'warn' | 'bad' | 'neutral'
  title: string
}

interface SectionView {
  titleKey: string
  metrics: SectionMetric[]
}

const basic = computed<BasicItem[]>(() => {
  const row = props.row
  if (!row) {
    return []
  }
  const items: BasicItem[] = []
  for (const def of profile.value.basic?.defs ?? []) {
    const column = def.aliases.map(alias => columnIndex.value.get(normalize(alias))).find(Boolean)
    if (!column) {
      continue
    }
    const raw = String(row[column.key] ?? '').trim()
    if (!raw) {
      continue
    }
    items.push({ label: metricLabel(def), value: formatValue(raw), unit: def.unit })
  }
  return items
})

function metricLabel(def: PredictDetailMetricDef): string {
  return def.labelKey ? t(def.labelKey) : (def.label ?? '')
}

function buildMetrics(defs: PredictDetailMetricDef[], row: CsvPreviewRow): SectionMetric[] {
  const metrics: SectionMetric[] = []
  for (const def of defs) {
    const column = def.aliases.map(alias => columnIndex.value.get(normalize(alias))).find(Boolean)
    if (!column) {
      continue
    }
    const raw = String(row[column.key] ?? '').trim()
    if (!raw) {
      continue
    }
    const label = metricLabel(def)
    metrics.push({
      label,
      raw,
      value: formatValue(raw),
      unit: def.unit,
      status: statusOf(raw, def.polarity ?? 'neutral'),
      title: `${label}: ${raw}`
    })
  }
  return metrics
}

/** 未知能力族：按 CSV 列自动生成一个「全部字段」分组。 */
function buildGenericMetrics(row: CsvPreviewRow): SectionMetric[] {
  const skip = new Set(['smiles'])
  for (const def of profile.value.basic?.defs ?? []) {
    for (const alias of def.aliases) {
      skip.add(normalize(alias))
    }
  }
  const metrics: SectionMetric[] = []
  for (const column of props.columns) {
    if (skip.has(normalize(column.key)) || skip.has(normalize(column.originalKey))) {
      continue
    }
    const raw = String(row[column.key] ?? '').trim()
    if (!raw) {
      continue
    }
    const label = column.title || column.originalKey || column.key
    metrics.push({
      label,
      raw,
      value: formatValue(raw),
      status: 'neutral',
      title: `${label}: ${raw}`
    })
  }
  return metrics
}

const sections = computed<SectionView[]>(() => {
  const row = props.row
  if (!row) {
    return []
  }
  if (profile.value.generic) {
    const metrics = buildGenericMetrics(row)
    return metrics.length
      ? [{ titleKey: 'predict.result.detailSectionGeneric', metrics }]
      : []
  }
  const result: SectionView[] = []
  for (const section of profile.value.sections) {
    const metrics = buildMetrics(section.defs, row)
    if (metrics.length) {
      result.push({ titleKey: section.titleKey, metrics })
    }
  }
  return result
})

const metricCount = computed(
  () => sections.value.reduce((sum, section) => sum + section.metrics.length, basic.value.length)
)

const showLegend = computed(() =>
  sections.value.some(section => section.metrics.some(metric => metric.status !== 'neutral'))
)

const radarMetrics = computed(() => {
  const row = props.row
  if (!row) {
    return []
  }
  return profile.value.radar
    .map(([label, aliases]) => {
      const column = aliases.map(alias => columnIndex.value.get(normalize(alias))).find(Boolean)
      if (!column) {
        return null
      }
      const value = Number(row[column.key])
      if (!Number.isFinite(value)) {
        return null
      }
      return { label, value: Math.min(1, Math.max(0, value)) }
    })
    .filter((item): item is { label: string; value: number } => Boolean(item))
})

function formatValue(raw: string): string {
  const text = raw.trim()
  const value = Number(text)
  if (!text || !Number.isFinite(value)) {
    return text || '-'
  }
  if (value === 0) {
    return '0'
  }
  const abs = Math.abs(value)
  if (abs < 0.001) {
    return value.toExponential(2)
  }
  if (abs >= 100) {
    return value.toFixed(1)
  }
  return String(Number(value.toFixed(3)))
}

function statusOf(raw: string, polarity: PredictDetailPolarity): 'good' | 'warn' | 'bad' | 'neutral' {
  const value = Number(raw)
  if (polarity === 'neutral' || !Number.isFinite(value) || value < 0 || value > 1) {
    return 'neutral'
  }
  if (polarity === 'good') {
    if (value >= 0.7) return 'good'
    if (value >= 0.3) return 'warn'
    return 'bad'
  }
  if (value >= 0.7) return 'bad'
  if (value >= 0.3) return 'warn'
  return 'good'
}

function handleExportCsv(): void {
  if (!props.row) {
    return
  }
  const columns = props.columns.map(column => ({ key: column.key, title: column.title }))
  downloadCsv(`molecule-predict-${props.taskId}.csv`, columns, [props.row])
}

function handleExportPdf(): void {
  window.print()
}

function renderRadar(): void {
  if (view.value !== 'radar' || !radarRef.value || !radarMetrics.value.length) {
    return
  }
  if (!radarChart) {
    radarChart = echarts.init(radarRef.value)
  }
  radarChart.setOption(
    {
      radar: {
        indicator: radarMetrics.value.map(metric => ({ name: metric.label, max: 1 })),
        radius: '66%',
        axisName: { fontSize: 11 }
      },
      series: [
        {
          type: 'radar',
          data: [
            {
              value: radarMetrics.value.map(metric => metric.value),
              areaStyle: { opacity: 0.25 },
              lineStyle: { color: chartColors.primary },
              itemStyle: { color: chartColors.primary }
            }
          ]
        }
      ]
    },
    true
  )
  radarChart.resize()
}

watch(
  () => [view.value, props.row] as const,
  async () => {
    await nextTick()
    renderRadar()
  }
)

watch(open, async value => {
  if (value) {
    await nextTick()
    renderRadar()
  }
})

onMounted(() => {
  isDark.value = readTheme()
  if (typeof MutationObserver !== 'undefined') {
    themeObserver = new MutationObserver(() => {
      isDark.value = readTheme()
      renderRadar()
    })
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme']
    })
  }
})

onBeforeUnmount(() => {
  themeObserver?.disconnect()
  themeObserver = null
  radarChart?.dispose()
  radarChart = null
})
</script>

<template>
  <a-drawer
    v-model:open="open"
    :title="t(profile.titleKey)"
    placement="right"
    :width="'min(1360px, 96vw)'"
    :body-style="{ padding: '0' }"
    destroy-on-close
  >
    <div v-if="row" ref="detailRef" class="admet-detail" :class="{ 'admet-detail--dark': isDark }">
      <div class="admet-detail__toolbar">
        <div v-if="profile.showSmiles" class="admet-detail__smiles">{{ smiles || '-' }}</div>
        <div class="admet-detail__actions">
          <a-radio-group v-if="profile.showRadar" v-model:value="view" size="small" button-style="solid">
            <a-radio-button value="table">{{ t('predict.result.detailTable') }}</a-radio-button>
            <a-radio-button value="radar">{{ t('predict.result.detailRadar') }}</a-radio-button>
          </a-radio-group>
          <a-button size="small" @click="handleExportCsv">{{ t('predict.result.detailDownloadCsv') }}</a-button>
          <a-button size="small" @click="handleExportPdf">{{ t('predict.result.detailDownloadPdf') }}</a-button>
        </div>
      </div>

      <div v-if="profile.showRadar && view === 'radar'" class="admet-detail__radar-wrap">
        <a-empty v-if="!radarMetrics.length" :description="t('predict.result.detailNoData')" />
        <div v-else ref="radarRef" class="admet-detail__radar" />
      </div>

      <AffinityPredictDetail
        v-else-if="profile.key === 'affinity'"
        :row="row"
        :rows="rows ?? [row]"
        :task-id="taskId"
        :tool-name="toolName"
        @select-candidate="emit('selectCandidate', $event)"
      />

      <div v-else class="admet-detail__body">
        <aside class="admet-detail__aside">
          <section v-if="profile.showSmiles" class="admet-block admet-block--structure">
            <h3>{{ t('predict.result.detailSectionStructure') }}</h3>
            <div class="admet-block__structure">
              <Smiles2DCell :smiles="smiles" block />
            </div>
          </section>

          <section v-if="basic.length" class="admet-block admet-block--physchem">
            <h3>{{ t(profile.basic?.titleKey ?? 'predict.result.detailSectionBasic') }}</h3>
            <dl class="admet-list">
              <template v-for="item in basic" :key="item.label">
                <dt>{{ item.label }}</dt>
                <dd>{{ item.value }}<span v-if="item.unit" class="admet-unit"> {{ item.unit }}</span></dd>
              </template>
            </dl>
          </section>

          <section class="admet-block admet-block--report">
            <h3>{{ t('predict.result.detailReportInfo') }}</h3>
            <dl class="admet-list">
              <dt>{{ t('predict.result.detailTask') }}</dt>
              <dd class="admet-mono">{{ taskId }}</dd>
              <dt>{{ t('predict.result.detailTool') }}</dt>
              <dd>{{ toolName || '-' }}</dd>
              <dt>{{ t('predict.result.detailMetricCount') }}</dt>
              <dd>{{ metricCount }}</dd>
              <dt>{{ t('predict.result.detailSource') }}</dt>
              <dd>{{ t('predict.result.detailSourceValue') }}</dd>
            </dl>
          </section>
        </aside>

        <div class="admet-detail__sections">
          <section
            v-for="section in sections"
            :key="section.titleKey"
            class="admet-block"
            :class="`admet-block--${section.titleKey.split('.').pop()?.toLowerCase()}`"
          >
            <h3>{{ t(section.titleKey) }}</h3>
            <dl class="admet-list">
              <template v-for="metric in section.metrics" :key="metric.label">
                <dt :title="metric.title">{{ metric.label }}</dt>
                <dd>
                  <span class="admet-value">{{ metric.value }}</span>
                  <span v-if="metric.unit" class="admet-unit">{{ metric.unit }}</span>
                  <span class="admet-dot" :class="`admet-dot--${metric.status}`" :title="metric.title" />
                </dd>
              </template>
            </dl>
          </section>
        </div>
      </div>

      <div v-if="showLegend" class="admet-detail__legend">
        <span><i class="admet-dot admet-dot--good" /> {{ t('predict.result.detailLegendGood') }}</span>
        <span><i class="admet-dot admet-dot--warn" /> {{ t('predict.result.detailLegendWarn') }}</span>
        <span><i class="admet-dot admet-dot--bad" /> {{ t('predict.result.detailLegendBad') }}</span>
        <span><i class="admet-dot admet-dot--neutral" /> {{ t('predict.result.detailLegendNeutral') }}</span>
      </div>
    </div>
    <a-empty v-else :description="t('predict.result.detailNoData')" />
  </a-drawer>
  <ResultDisclaimer />
</template>

<style scoped lang="less">
.admet-detail {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 100%;
  padding: 18px 22px 28px;
  background: #fff;
  color: #1f2937;
}

.admet-detail--dark {
  background: #141414;
  color: #e6e6e6;
}

.admet-detail--dark .admet-detail__toolbar,
.admet-detail--dark .admet-block {
  border-color: #303030;
}

.admet-detail--dark .admet-detail__smiles,
.admet-detail--dark .admet-detail__legend,
.admet-detail--dark .admet-list dt {
  color: #a3a3a3;
}

.admet-detail--dark .admet-block {
  background: #1b1b1b;
}

.admet-detail--dark .admet-block--structure {
  background: #101010;
}

.admet-detail--dark .admet-list dt,
.admet-detail--dark .admet-list dd {
  border-color: #2a2a2a;
}

.admet-detail--dark .admet-list dd {
  color: #f0f0f0;
}

.admet-detail--dark .admet-detail__radar-wrap {
  border-color: #303030;
}

.admet-detail__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--ant-color-border-secondary, #e5e7eb);
}

.admet-detail__smiles {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-all;
  color: var(--ant-color-text-secondary, #6b7280);
}

.admet-detail__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.admet-detail__body {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.admet-detail__aside {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.admet-detail__sections {
  columns: 2;
  column-gap: 16px;
}

.admet-block {
  break-inside: avoid;
  margin-bottom: 14px;
  border: 1px solid var(--ant-color-border-secondary, #e5e7eb);
  border-radius: 8px;
  overflow: hidden;
  background: var(--ant-color-bg-container, #fff);
}

.admet-block h3 {
  margin: 0;
  padding: 7px 11px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #fff;
  background: #4b5563;
}

.admet-block--detailsectionabsorption h3 { background: #6aa6a0; }
.admet-block--detailsectiondistribution h3 { background: #f0b27a; }
.admet-block--detailsectionmetabolism h3 { background: #5b8db8; }
.admet-block--detailsectionexcretion h3 { background: #e07b63; }
.admet-block--detailsectiontoxicity h3 { background: #b39ddb; }
.admet-block--detailsectiontox21 h3 { background: #c9b8a8; }
.admet-block--detailsectionecotoxicity h3 { background: #8fb98f; }
.admet-block--detailsectionld50 h3 { background: #a3a3a3; }
.admet-block--physchem h3 { background: #4b5563; }
.admet-block--structure h3 { background: #334155; }

.admet-block__structure {
  padding: 10px;
}

.admet-list {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  margin: 0;
  padding: 0;
}

.admet-list dt,
.admet-list dd {
  margin: 0;
  padding: 4px 10px;
  font-size: 12px;
  line-height: 18px;
  border-top: 1px solid var(--ant-color-border-secondary, #f0f0f0);
}

.admet-list dt {
  color: var(--ant-color-text-secondary, #4b5563);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admet-list dd {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  font-variant-numeric: tabular-nums;
  color: var(--ant-color-text, #111827);
}

.admet-value {
  font-weight: 600;
}

.admet-unit {
  font-size: 10px;
  color: var(--ant-color-text-tertiary, #9ca3af);
}

.admet-mono {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 10px;
  word-break: break-all;
  text-align: right;
}

.admet-block--report .admet-list {
  grid-template-columns: 78px minmax(0, 1fr);
}

.admet-block--report .admet-list dd {
  justify-content: flex-start;
  text-align: left;
  word-break: break-all;
}

.admet-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #cbd5e1;
}

.admet-dot--good { background: #18a058; }
.admet-dot--warn { background: #f0a020; }
.admet-dot--bad { background: #e5484d; }
.admet-dot--neutral { background: #cbd5e1; }

.admet-detail__radar-wrap {
  min-height: 420px;
  border: 1px solid var(--ant-color-border-secondary, #e5e7eb);
  border-radius: 8px;
  padding: 12px;
}

.admet-detail__radar {
  width: 100%;
  height: 420px;
}

.admet-detail__legend {
  display: flex;
  gap: 18px;
  align-items: center;
  padding-top: 8px;
  font-size: 12px;
  color: var(--ant-color-text-secondary, #6b7280);
}

.admet-detail__legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

@media (max-width: 900px) {
  .admet-detail__body { grid-template-columns: minmax(0, 1fr); }
  .admet-detail__sections { columns: 1; }
}

@media print {
  :global(body *) { visibility: hidden !important; }
  .admet-detail,
  .admet-detail * { visibility: visible !important; }
  .admet-detail {
    position: absolute;
    inset: 0 auto auto 0;
    width: 100%;
    padding: 0;
    background: #fff;
  }
  .admet-detail__actions { display: none !important; }
}
</style>
