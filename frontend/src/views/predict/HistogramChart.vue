<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { buildHistogram } from './histogram'
import { chartColors } from '@/utils/chartTheme'

const props = withDefaults(
  defineProps<{ values: number[]; title?: string; bins?: number; height?: number }>(),
  { title: '', bins: 10, height: 180 }
)

const chartRef = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function render(): void {
  const host = chartRef.value
  if (!host) {
    return
  }
  if (!chart) {
    chart = echarts.init(host)
  }
  const bins = buildHistogram(props.values, props.bins)
  chart.setOption(
    {
      title: {
        text: props.title,
        left: 'center',
        top: 2,
        textStyle: { fontSize: 12, fontWeight: 'normal' }
      },
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 12, top: 30, bottom: 40 },
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
          itemStyle: { color: chartColors.primary }
        }
      ]
    },
    true
  )
}

function resize(): void {
  chart?.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', resize)
})

watch(
  () => [props.values, props.title, props.bins, props.height] as const,
  () => {
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
  <div ref="chartRef" class="histogram-chart" data-testid="predict-histogram" :style="{ height: `${height}px` }" />
</template>

<style scoped>
.histogram-chart {
  width: 100%;
  min-height: 180px;
}
</style>
