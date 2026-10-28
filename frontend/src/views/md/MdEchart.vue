<template>
  <div ref="chartEl" class="md-echart" :style="{ height }" role="img"></div>
</template>

<script setup lang="ts">
  import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import * as echarts from 'echarts'
  import type { EChartsOption } from 'echarts'

  const props = withDefaults(
    defineProps<{
      option: EChartsOption
      height?: string
    }>(),
    { height: '320px' }
  )

  const chartEl = ref<HTMLDivElement | null>(null)
  let chart: ReturnType<typeof echarts.init> | null = null

  function render(): void {
    if (!chartEl.value) return
    if (!chart) {
      chart = echarts.init(chartEl.value)
    }
    chart.setOption(props.option, true)
    chart.resize()
  }

  function handleResize(): void {
    chart?.resize()
  }

  onMounted(() => {
    render()
    window.addEventListener('resize', handleResize)
  })

  watch(
    () => props.option,
    () => render(),
    { deep: true }
  )

  onBeforeUnmount(() => {
    window.removeEventListener('resize', handleResize)
    chart?.dispose()
    chart = null
  })
</script>

<style scoped lang="less">
  .md-echart {
    width: 100%;
    min-height: 220px;
  }
</style>
