<template>
  <div class="free-energy" data-testid="free-energy-page">
    <app-page-header :title="t('md.freeEnergy.title')" :subtitle="t('md.freeEnergy.subtitle')">
      <template #actions>
        <a-button v-if="taskId" @click="reload" :loading="loading">{{ t('md.common.refresh') }}</a-button>
        <a-button type="primary" :disabled="rows.length === 0" @click="exportCsv" data-testid="free-energy-export">
          {{ t('md.freeEnergy.exportCsv') }}
        </a-button>
      </template>
    </app-page-header>

    <mock-data-banner :mock="isMock" :disclaimer="t('md.common.mockDisclaimer')" />

    <skeleton-detail v-if="loading && !result" />

    <a-result v-else-if="loadError" status="warning" :title="t('md.common.loadFailed')" :sub-title="loadError">
      <template #extra>
        <a-button type="primary" @click="reload">{{ t('md.common.retry') }}</a-button>
      </template>
    </a-result>

    <template v-else>
      <a-empty v-if="rows.length === 0" :description="t('md.freeEnergy.noData')" />

      <template v-else>
        <a-row :gutter="16" class="free-energy__grid">
          <a-col :xs="24" :md="8">
            <a-card :bordered="false" class="free-energy__stat" data-testid="free-energy-total">
              <p class="free-energy__stat-label">{{ t('md.freeEnergy.totalDeltaG') }}</p>
              <p class="free-energy__stat-value">
                {{ formatNumber(summary.mean) }}
                <span class="free-energy__stat-unit">{{ t('md.freeEnergy.unit') }}</span>
              </p>
              <p class="free-energy__stat-sub">
                ± {{ formatNumber(summary.standardError) }} ({{ t('md.freeEnergy.standardError') }})
              </p>
            </a-card>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-card :bordered="false" class="free-energy__stat">
              <p class="free-energy__stat-label">{{ t('md.freeEnergy.frameCount') }}</p>
              <p class="free-energy__stat-value">{{ summary.frameCount }}</p>
            </a-card>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-card :bordered="false" class="free-energy__stat">
              <p class="free-energy__stat-label">{{ t('md.freeEnergy.stdDev') }}</p>
              <p class="free-energy__stat-value">
                {{ formatNumber(summary.stdDev) }}
                <span class="free-energy__stat-unit">{{ t('md.freeEnergy.unit') }}</span>
              </p>
            </a-card>
          </a-col>
        </a-row>

        <a-row :gutter="16" class="free-energy__grid">
          <a-col :xs="24" :lg="12">
            <a-card :bordered="false" :title="t('md.freeEnergy.decompositionTitle')" size="small">
              <md-echart v-if="decompositionOption" :option="decompositionOption" height="340px" />
              <a-empty v-else :description="t('md.freeEnergy.noData')" />
            </a-card>
          </a-col>
          <a-col :xs="24" :lg="12">
            <a-card :bordered="false" :title="t('md.freeEnergy.convergenceTitle')" size="small">
              <md-echart v-if="convergenceOption" :option="convergenceOption" height="340px" />
              <a-empty v-else :description="t('md.freeEnergy.noData')" />
            </a-card>
          </a-col>
        </a-row>

        <p class="free-energy__note">{{ t('md.freeEnergy.sourceNote') }}</p>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import type { EChartsOption } from 'echarts'
  import Papa from 'papaparse'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import MockDataBanner from '@/components/common/MockDataBanner.vue'
  import MdEchart from './MdEchart.vue'
  import { chartColors } from '@/utils/chartTheme'
  import { getArtifactDetail, getMdResult } from '@/api/md'
  import { fetchProtectedFileText } from '@/utils/protected-file-access'
  import {
    buildFreeEnergyRows,
    cumulativeMean,
    energyComponentMeans,
    findOutputByStandardType,
    rowsToCsv,
    summarizeDeltaG
  } from './analysis'
  import type { EnergyComponentMean, FreeEnergyComponentKey } from './analysis'
  import type { ArtifactVersionFile } from '@/types/artifacts'
  import type { FreeEnergyRow, MdResultDetail } from '@/types/md'

  interface PapaParseResult {
    data: Array<Record<string, string>>
  }

  const { t } = useI18n()
  const route = useRoute()
  const taskId = computed(() => String(route.params.id ?? ''))

  const result = ref<MdResultDetail | null>(null)
  const files = ref<ArtifactVersionFile[]>([])
  const rows = ref<FreeEnergyRow[]>([])
  const loading = ref(false)
  const loadError = ref('')

  const isMock = computed(() => Boolean(result.value?.mock))

  const EXPORT_COLUMNS = [
    'frame',
    'delta_g_total',
    'delta_g_vdw',
    'delta_g_electrostatic',
    'delta_g_polar_solvation',
    'delta_g_nonpolar_solvation',
    'delta_g_sasa'
  ]

  const COMPONENT_LABEL_KEYS: Record<FreeEnergyComponentKey, string> = {
    delta_g_vdw: 'md.freeEnergy.vdw',
    delta_g_electrostatic: 'md.freeEnergy.electrostatic',
    delta_g_polar_solvation: 'md.freeEnergy.polarSolvation',
    delta_g_nonpolar_solvation: 'md.freeEnergy.nonpolarSolvation',
    delta_g_sasa: 'md.freeEnergy.sasa'
  }

  const summary = computed(() => summarizeDeltaG(rows.value.map((row) => row.delta_g_total)))

  function formatNumber(value: number): string {
    if (!Number.isFinite(value)) return '—'
    return value.toFixed(2)
  }

  const componentMeans = computed<EnergyComponentMean[]>(() => energyComponentMeans(rows.value))

  const decompositionOption = computed<EChartsOption | null>(() => {
    const means = componentMeans.value
    if (means.length === 0 || means.every((item) => !Number.isFinite(item.mean))) return null
    return {
      grid: { left: 56, right: 16, top: 24, bottom: 64 },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: means.map((item) => t(COMPONENT_LABEL_KEYS[item.key])),
        axisLabel: { interval: 0, rotate: 20, fontSize: 10 }
      },
      yAxis: { type: 'value', name: t('md.freeEnergy.axisY') },
      series: [
        {
          type: 'bar',
          data: means.map((item) => (Number.isFinite(item.mean) ? Number(item.mean.toFixed(3)) : 0)),
          itemStyle: { color: chartColors.primary }
        }
      ]
    }
  })

  const convergenceOption = computed<EChartsOption | null>(() => {
    if (rows.value.length === 0) return null
    const cumulative = cumulativeMean(rows.value.map((row) => row.delta_g_total))
    const points = rows.value
      .map((row, index) => ({ frame: row.frame, value: cumulative[index] }))
      .filter((point) => Number.isFinite(point.value))
    if (points.length === 0) return null
    return {
      grid: { left: 56, right: 16, top: 24, bottom: 40 },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'value', name: t('md.freeEnergy.axisFrame'), nameLocation: 'middle', nameGap: 24 },
      yAxis: { type: 'value', name: t('md.freeEnergy.axisY') },
      series: [
        {
          type: 'line',
          smooth: true,
          showSymbol: false,
          data: points.map((point) => [point.frame, point.value]),
          itemStyle: { color: chartColors.purple }
        }
      ]
    }
  })

  function parseCsv(text: string): Array<Record<string, string>> {
    const parser = Papa as unknown as { parse: (input: string, config: Record<string, unknown>) => PapaParseResult }
    return parser.parse(text, { header: true, skipEmptyLines: true }).data
  }

  function pickTableFile(list: ArtifactVersionFile[]): ArtifactVersionFile | null {
    return (
      list.find((file) => file.role === 'table_file') ??
      list.find((file) => file.role === 'molecule_table') ??
      list.find((file) => file.role === 'smiles_csv') ??
      list.find((file) => (file.filename ?? '').toLowerCase().endsWith('.csv')) ??
      null
    )
  }

  async function reload(): Promise<void> {
    if (!taskId.value) return
    loading.value = true
    loadError.value = ''
    try {
      const detail = await getMdResult(taskId.value)
      result.value = detail
      const output =
        detail.outputs.find((item) => item.semantic_type === 'energies') ??
        findOutputByStandardType(detail.outputs, 'molecule_table@1')
      if (!output) {
        files.value = []
        rows.value = []
        return
      }
      const artifact = await getArtifactDetail(output.id)
      files.value = artifact.latest_version.files ?? []
      const tableFile = pickTableFile(files.value)
      if (!tableFile) {
        rows.value = []
        return
      }
      const text = await fetchProtectedFileText(tableFile.download_url)
      rows.value = buildFreeEnergyRows(parseCsv(text) as Array<Record<string, unknown>>)
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : String(error)
    } finally {
      loading.value = false
    }
  }

  function exportCsv(): void {
    if (rows.value.length === 0) return
    const csv = rowsToCsv(rows.value as unknown as Array<Record<string, unknown>>, EXPORT_COLUMNS)
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `free-energy-${taskId.value}.csv`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  }

  onMounted(() => {
    void reload()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .free-energy {
    max-width: @container-xxl;
    margin: 0 auto;
  }

  .free-energy__grid {
    margin-bottom: @spacing-md;
  }

  .free-energy__stat {
    height: 100%;
    border-radius: @border-radius-lg;
  }

  .free-energy__stat-label {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .free-energy__stat-value {
    margin: @spacing-xs 0 0;
    color: @text-color-light-primary;
    font-size: @font-size-xxxl;
    font-weight: @font-weight-bold;
    line-height: @line-height-tight;
  }

  .free-energy__stat-unit {
    font-size: @font-size-sm;
    font-weight: @font-weight-regular;
    color: @text-color-light-secondary;
  }

  .free-energy__stat-sub {
    margin: @spacing-xs 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .free-energy__note {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }
</style>
