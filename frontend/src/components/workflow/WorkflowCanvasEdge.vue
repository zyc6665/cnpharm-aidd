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
    <g
      class="edge-delete-control"
      :data-edge-delete="edgeId"
      role="button"
      tabindex="0"
      :aria-label="t('workflow.canvasEdge.delete', { edgeId })"
      @click.stop="$emit('delete-edge')"
      @keydown.enter.prevent="$emit('delete-edge')"
      @keydown.space.prevent="$emit('delete-edge')"
    >
      <circle :cx="deletePosition.x" :cy="deletePosition.y" r="9" />
      <text :x="deletePosition.x" :y="deletePosition.y + 4" text-anchor="middle">×</text>
    </g>
  </g>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'

  const props = defineProps<{
    edgeId: string
    source: { x: number; y: number }
    target: { x: number; y: number }
    label?: string
    active?: boolean
  }>()

  defineEmits<{
    (event: 'delete-edge'): void
  }>()

  const { t } = useI18n()

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

  const deletePosition = computed(() => ({
    x: (props.source.x + props.target.x) / 2,
    y: (props.source.y + props.target.y) / 2 + 14
  }))
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-canvas-edge { pointer-events: none; }

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
    stroke: @bg-surface;
    stroke-width: 4px;
  }

  .is-active .edge-path {
    stroke: @accent-color;
  }

  .edge-delete-control {
    cursor: pointer;
    pointer-events: auto;
  }

  .edge-delete-control circle {
    fill: @bg-surface;
    stroke: rgba(255, 77, 79, 0.35);
    stroke-width: 1.5;
  }

  .edge-delete-control text {
    fill: @error-color;
    font-size: 13px;
    font-weight: 800;
    pointer-events: none;
  }

  .edge-delete-control:hover circle,
  .edge-delete-control:focus-visible circle {
    fill: @error-color;
    outline: none;
  }

  .edge-delete-control:hover text,
  .edge-delete-control:focus-visible text {
    fill: #fff;
  }
</style>
