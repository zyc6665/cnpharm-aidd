<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { FunnelStage } from './funnel'

const props = withDefaults(
  defineProps<{ stages: FunnelStage[]; labels?: Record<string, string> }>(),
  { labels: () => ({}) }
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
  const data = props.stages.map(stage => ({
    name: props.labels[stage.key] ?? stage.key,
    value: stage.remaining
  }))
  chart.setOption(
    {
      tooltip: { trigger: 'item', formatter: '{b}: {c}' },
      color: ['#5b8ff9', '#61ddaa', '#f6bd16', '#ff9845'],
      series: [
        {
          type: 'funnel',
          left: '8%',
          right: '8%',
          top: 8,
          bottom: 8,
          sort: 'none',
          minSize: '32%',
          gap: 2,
          label: { position: 'inside', formatter: '{b}: {c}' },
          data
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
  () => [props.stages, props.labels] as const,
  () => render(),
  { deep: true }
)

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="chartRef" class="funnel-chart" data-testid="screening-funnel" />
</template>

<style scoped>
.funnel-chart {
  width: 100%;
  height: 300px;
}
</style>
