<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { buildHistogram } from './histogram'
import { chartColors } from '@/utils/chartTheme'

export interface DistributionPoint {
  label: string
  value: number
}

const props = withDefaults(
  defineProps<{ points: DistributionPoint[]; height?: number; bins?: number; medianLabel?: string }>(),
  { height: 300, bins: 12, medianLabel: '' }
)

const chartRef = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

const sorted = computed(() => [...props.points].sort((left, right) => left.value - right.value))

const median = computed(() => {
  const values = sorted.value.map(point => point.value)
  if (!values.length) {
    return null
  }
  const middle = Math.floor(values.length / 2)
  return values.length % 2 ? values[middle]! : ((values[middle - 1] ?? 0) + (values[middle] ?? 0)) / 2
})

function formatNumber(value: number): string {
  return Number(value.toFixed(3)).toString()
}

function medianMarkLine() {
  if (median.value === null) {
    return undefined
  }
  return {
    symbol: 'none' as const,
    lineStyle: { type: 'dashed' as const, color: '#f0a020', width: 1.5 },
    label: {
      formatter: `${props.medianLabel} ${formatNumber(median.value)}`,
      position: 'insideEndTop' as const,
      color: '#f0a020',
      fontSize: 11
    },
    data: [{ xAxis: median.value }]
  }
}

function render(): void {
  const host = chartRef.value
  if (!host) {
    return
  }
  if (!chart) {
    chart = echarts.init(host)
  }
  if (!sorted.value.length) {
    chart.clear()
    return
  }

  const dotPlot = sorted.value.length <= 30
  const values = sorted.value.map(point => point.value)
  const valueMin = Math.min(...values)
  const valueMax = Math.max(...values)
  const padding = Math.max((valueMax - valueMin) * 0.15, 0.1)
  const option: echarts.EChartsOption = dotPlot
    ? {
        grid: { left: 110, right: 86, top: 24, bottom: 36 },
        tooltip: { trigger: 'item', formatter: (params: unknown) => {
          const item = params as { name?: string; value?: number }
          return `${item.name ?? ''}<br/>${formatNumber(Number(item.value ?? 0))}`
        } },
        xAxis: {
          type: 'value',
          min: Number((valueMin - padding).toFixed(2)),
          max: Number((valueMax + padding).toFixed(2)),
          axisLabel: { fontSize: 10, formatter: (value: number) => formatNumber(value) }
        },
        yAxis: {
          type: 'category',
          inverse: true,
          data: sorted.value.map(point => point.label),
          axisLabel: { fontSize: 11, width: 92, overflow: 'truncate' }
        },
        series: [
          {
            type: 'scatter',
            data: sorted.value.map(point => point.value),
            symbolSize: 11,
            itemStyle: { color: chartColors.primary },
            label: {
              show: true,
              position: 'right',
              fontSize: 11,
              color: '#8c8c8c',
              formatter: (params: unknown) => formatNumber(Number((params as { value?: number }).value ?? 0))
            },
            markLine: medianMarkLine()
          }
        ]
      }
    : (() => {
        const bins = buildHistogram(sorted.value.map(point => point.value), props.bins)
        return {
          grid: { left: 46, right: 24, top: 24, bottom: 42 },
          tooltip: { trigger: 'axis' },
          xAxis: {
            type: 'category',
            data: bins.map(bin => bin.label),
            axisLabel: { fontSize: 10, rotate: 30 }
          },
          yAxis: { type: 'value', minInterval: 1 },
          series: [
            {
              type: 'bar',
              data: bins.map(bin => bin.count),
              barWidth: '62%',
              itemStyle: { color: chartColors.primary },
              markLine: medianMarkLine()
            }
          ]
        }
      })()

  chart.setOption(option, true)
}

function resize(): void {
  chart?.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', resize)
})

watch(
  () => [props.points, props.height, props.bins, props.medianLabel] as const,
  async () => {
    await nextTick()
    render()
    resize()
  },
  { deep: true, flush: 'post' }
)

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="chartRef" class="metric-distribution-chart" data-testid="predict-distribution-chart" :style="{ height: `${height}px` }" />
</template>

<style scoped>
.metric-distribution-chart {
  width: 100%;
}
</style>
