---
name: molecule-admet-detail
description: 单分子 ADMET 详细报告抽屉，按吸收/分布/代谢/排泄/毒性/Tox21/生态毒性分组展示预测结果，支持雷达视图与单分子 CSV/PDF 导出。
---

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts'
import Smiles2DCell from '@/components/tasks/Smiles2DCell.vue'
import { downloadCsv } from '@/views/predict/csv-export'
import { chartColors } from '@/utils/chartTheme'
import type { CsvPreviewColumn, CsvPreviewRow } from '@/domain/tasks/csv-result'

type Polarity = 'good' | 'risk' | 'neutral'

interface MetricDef {
  label: string
  aliases: string[]
  polarity?: Polarity
  unit?: string
}

interface MetricSection {
  titleKey: string
  defs: MetricDef[]
}

const props = defineProps<{
  row: CsvPreviewRow | null
  columns: CsvPreviewColumn[]
  taskId: string
}>()

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

const SECTIONS: MetricSection[] = [
  {
    titleKey: 'predict.result.detailSectionBasic',
    defs: [
      { label: 'Molecular Weight (MW)', aliases: ['mol_weight', 'molecularweight', 'mw'], unit: 'g/mol' },
      { label: 'LogP', aliases: ['logp', 'xlogp'] },
      { label: 'TPSA', aliases: ['tpsa'], unit: 'Å²' },
      { label: 'H-bond Donors', aliases: ['hbd', 'hbonddonors'] },
      { label: 'H-bond Acceptors', aliases: ['hba', 'hbondacceptors'] },
      { label: 'Rotatable Bonds', aliases: ['rotb', 'rotatablebonds'] },
      { label: 'QED', aliases: ['qed'] },
      { label: 'SA Score', aliases: ['sa_score', 'sascore'] },
      { label: 'InChIKey', aliases: ['inchi_key', 'inchikey'] }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionAbsorption',
    defs: [
      { label: 'F20', aliases: ['F20'], polarity: 'good' },
      { label: 'F30', aliases: ['F30'], polarity: 'good' },
      { label: 'HIA', aliases: ['HIA'], polarity: 'good' },
      { label: 'PAMPA', aliases: ['PAMPA_NCATS', 'PAMPA'], polarity: 'good' },
      { label: 'P-gp Inhibitor', aliases: ['Pgp-inhibitor', 'PgpInhibitor'], polarity: 'risk' },
      { label: 'P-gp Substrate', aliases: ['Pgp-substrate', 'PgpSubstrate'] },
      { label: 'Caco-2 Permeability', aliases: ['Caco2', 'Caco-2'] },
      { label: 'MDCK Permeability (cm/s)', aliases: ['MDCK Permeability', 'MDCK'] }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionDistribution',
    defs: [
      { label: 'BBB', aliases: ['BBB'], polarity: 'good' },
      { label: 'Fraction Unbound (Fu)', aliases: ['Fu'], polarity: 'good' },
      { label: 'PPB', aliases: ['PPB'], unit: '%' },
      { label: 'VDss', aliases: ['VD', 'VDss'], unit: 'L/kg' }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionMetabolism',
    defs: [
      { label: 'CYP1A2 Inhibitor', aliases: ['CYP1A2 inhibitor'], polarity: 'risk' },
      { label: 'CYP1A2 Substrate', aliases: ['CYP1A2 substrate'] },
      { label: 'CYP2C19 Inhibitor', aliases: ['CYP2C19 inhibitor'], polarity: 'risk' },
      { label: 'CYP2C19 Substrate', aliases: ['CYP2C19 substrate'] },
      { label: 'CYP2C9 Inhibitor', aliases: ['CYP2C9 inhibitor'], polarity: 'risk' },
      { label: 'CYP2C9 Substrate', aliases: ['CYP2C9 substrate'] },
      { label: 'CYP2D6 Inhibitor', aliases: ['CYP2D6 inhibitor'], polarity: 'risk' },
      { label: 'CYP2D6 Substrate', aliases: ['CYP2D6 substrate'] },
      { label: 'CYP3A4 Inhibitor', aliases: ['CYP3A4 inhibitor'], polarity: 'risk' },
      { label: 'CYP3A4 Substrate', aliases: ['CYP3A4 substrate'] }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionExcretion',
    defs: [
      { label: 'T1/2', aliases: ['T0.5', 'T1/2', 'halflife'], unit: 'h' },
      { label: 'CL', aliases: ['CL', 'clearance'], unit: 'mL/min/kg' }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionToxicity',
    defs: [
      { label: 'AMES', aliases: ['AMES'], polarity: 'risk' },
      { label: 'Carcinogenicity', aliases: ['Carcinogenicity'], polarity: 'risk' },
      { label: 'ClinTox', aliases: ['ClinTox'], polarity: 'risk' },
      { label: 'DILI', aliases: ['DILI'], polarity: 'risk' },
      { label: 'Eye Corrosion', aliases: ['Eye Corrosion'], polarity: 'risk' },
      { label: 'Eye Irritation', aliases: ['Eye Irritation'], polarity: 'risk' },
      { label: 'FDAMDD', aliases: ['FDAMDD'], polarity: 'risk' },
      { label: 'H-HT-2', aliases: ['H-HT-2'], polarity: 'risk' },
      { label: 'hERG Blockers', aliases: ['hERG'], polarity: 'risk' },
      { label: 'Respiratory Toxicity', aliases: ['Respiratory'], polarity: 'risk' },
      { label: 'ROA', aliases: ['ROA'], polarity: 'risk' },
      { label: 'Skin Sensitization', aliases: ['Skin Sensitization'], polarity: 'risk' }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionTox21',
    defs: [
      { label: 'NR-AhR', aliases: ['NR-AhR'], polarity: 'risk' },
      { label: 'NR-AR', aliases: ['NR-AR'], polarity: 'risk' },
      { label: 'NR-AR-LBD', aliases: ['NR-AR-LBD'], polarity: 'risk' },
      { label: 'NR-Aromatase', aliases: ['NR-Aromatase'], polarity: 'risk' },
      { label: 'NR-ER', aliases: ['NR-ER'], polarity: 'risk' },
      { label: 'NR-ER-LBD', aliases: ['NR-ER-LBD'], polarity: 'risk' },
      { label: 'NR-PPAR-gamma', aliases: ['NR-PPAR-gamma'], polarity: 'risk' },
      { label: 'SR-ARE', aliases: ['SR-ARE'], polarity: 'risk' },
      { label: 'SR-ATAD5', aliases: ['SR-ATAD5'], polarity: 'risk' },
      { label: 'SR-HSE', aliases: ['SR-HSE'], polarity: 'risk' },
      { label: 'SR-MMP', aliases: ['SR-MMP'], polarity: 'risk' },
      { label: 'SR-p53', aliases: ['SR-p53'], polarity: 'risk' }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionEcotoxicity',
    defs: [
      { label: 'BCF', aliases: ['BCF'], polarity: 'risk' },
      { label: 'IGC50', aliases: ['IGC50'], polarity: 'risk' },
      { label: 'LC50', aliases: ['LC50'], polarity: 'risk' },
      { label: 'LC50DM', aliases: ['LC50DM'], polarity: 'risk' }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionLd50',
    defs: [{ label: 'LD50 (Zhu)', aliases: ['LD50_zhu', 'LD50'], unit: 'log(mol/kg)' }]
  }
]

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
  for (const def of SECTIONS[0]?.defs ?? []) {
    const column = def.aliases.map(alias => columnIndex.value.get(normalize(alias))).find(Boolean)
    if (!column) {
      continue
    }
    const raw = String(row[column.key] ?? '').trim()
    if (!raw) {
      continue
    }
    items.push({ label: def.label, value: formatValue(raw), unit: def.unit })
  }
  return items
})

const sections = computed<SectionView[]>(() => {
  const row = props.row
  if (!row) {
    return []
  }
  const result: SectionView[] = []
  for (const section of SECTIONS.slice(1)) {
    const metrics: SectionMetric[] = []
    for (const def of section.defs) {
      const column = def.aliases.map(alias => columnIndex.value.get(normalize(alias))).find(Boolean)
      if (!column) {
        continue
      }
      const raw = String(row[column.key] ?? '').trim()
      if (!raw) {
        continue
      }
      metrics.push({
        label: def.label,
        raw,
        value: formatValue(raw),
        unit: def.unit,
        status: statusOf(raw, def.polarity ?? 'neutral'),
        title: `${def.label}: ${raw}`
      })
    }
    if (metrics.length) {
      result.push({ titleKey: section.titleKey, metrics })
    }
  }
  return result
})

const metricCount = computed(
  () => sections.value.reduce((sum, section) => sum + section.metrics.length, basic.value.length)
)

const radarMetrics = computed(() => {
  const row = props.row
  if (!row) {
    return []
  }
  const wanted: Array<[string, string[]]> = [
    ['HIA', ['HIA']],
    ['F20', ['F20']],
    ['F30', ['F30']],
    ['BBB', ['BBB']],
    ['Fu', ['Fu']],
    ['hERG', ['hERG']],
    ['DILI', ['DILI']],
    ['AMES', ['AMES']]
  ]
  return wanted
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

function statusOf(raw: string, polarity: Polarity): 'good' | 'warn' | 'bad' | 'neutral' {
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
  downloadCsv(`molecule-admet-${props.taskId}.csv`, columns, [props.row])
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
    :title="t('predict.result.detailTitle')"
    placement="right"
    :width="'min(1360px, 96vw)'"
    :body-style="{ padding: '0' }"
    destroy-on-close
  >
    <div v-if="row" ref="detailRef" class="admet-detail" :class="{ 'admet-detail--dark': isDark }">
      <div class="admet-detail__toolbar">
        <div class="admet-detail__smiles">{{ smiles || '-' }}</div>
        <div class="admet-detail__actions">
          <a-radio-group v-model:value="view" size="small" button-style="solid">
            <a-radio-button value="table">{{ t('predict.result.detailTable') }}</a-radio-button>
            <a-radio-button value="radar">{{ t('predict.result.detailRadar') }}</a-radio-button>
          </a-radio-group>
          <a-button size="small" @click="handleExportCsv">{{ t('predict.result.detailDownloadCsv') }}</a-button>
          <a-button size="small" @click="handleExportPdf">{{ t('predict.result.detailDownloadPdf') }}</a-button>
        </div>
      </div>

      <div v-if="view === 'radar'" class="admet-detail__radar-wrap">
        <a-empty v-if="!radarMetrics.length" :description="t('predict.result.detailNoData')" />
        <div v-else ref="radarRef" class="admet-detail__radar" />
      </div>

      <div v-else class="admet-detail__body">
        <aside class="admet-detail__aside">
          <section class="admet-block admet-block--structure">
            <h3>{{ t('predict.result.detailSectionStructure') }}</h3>
            <div class="admet-block__structure">
              <Smiles2DCell :smiles="smiles" block />
            </div>
          </section>

          <section v-if="basic.length" class="admet-block admet-block--physchem">
            <h3>{{ t('predict.result.detailSectionBasic') }}</h3>
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
              <dd>MolP-PC</dd>
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

      <div class="admet-detail__legend">
        <span><i class="admet-dot admet-dot--good" /> {{ t('predict.result.detailLegendGood') }}</span>
        <span><i class="admet-dot admet-dot--warn" /> {{ t('predict.result.detailLegendWarn') }}</span>
        <span><i class="admet-dot admet-dot--bad" /> {{ t('predict.result.detailLegendBad') }}</span>
        <span><i class="admet-dot admet-dot--neutral" /> {{ t('predict.result.detailLegendNeutral') }}</span>
      </div>
    </div>
    <a-empty v-else :description="t('predict.result.detailNoData')" />
  </a-drawer>
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
