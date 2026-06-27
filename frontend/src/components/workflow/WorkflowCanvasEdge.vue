<template>
  <g class="workflow-canvas-edge" :class="{ 'is-active': active }">
    <path class="edge-path edge-path-shadow" :d="pathDefinition" />
    <path class="edge-path" :d="pathDefinition" />
    <text
      v-if="label"
      class="edge-label"
      :x="labelPosition.x"
      :y="labelPosition.y"
      text-anchor="middle"
    >
      {{ label }}
    </text>
  </g>
</template>

<script setup lang="ts">
  import { computed } from 'vue'

  const props = defineProps<{
    source: { x: number; y: number }
    target: { x: number; y: number }
    label?: string
    active?: boolean
  }>()

  const pathDefinition = computed(() => {
    const controlOffset = Math.max(80, Math.abs(props.target.x - props.source.x) / 2)
    const c1x = props.source.x + controlOffset
    const c2x = props.target.x - controlOffset

    return `M ${props.source.x} ${props.source.y} C ${c1x} ${props.source.y}, ${c2x} ${props.target.y}, ${props.target.x} ${props.target.y}`
  })

  const labelPosition = computed(() => ({
    x: (props.source.x + props.target.x) / 2,
    y: (props.source.y + props.target.y) / 2 - 10
  }))
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-canvas-edge {
    pointer-events: none;
  }

  .edge-path {
    fill: none;
    stroke: rgba(59, 130, 246, 0.4);
    stroke-width: 2;
  }

  .edge-path-shadow {
    stroke: @border-color-hover;
    stroke-width: 9;
  }

  .edge-label {
    fill: @text-color-light-secondary;
    font-size: 11px;
    font-weight: 700;
    paint-order: stroke;
    stroke: rgba(255, 255, 255, 0.9);
    stroke-width: 4px;
  }

  .is-active .edge-path {
    stroke: @accent-color;
  }
</style>
