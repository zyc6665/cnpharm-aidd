<template>
  <div
    role="button"
    tabindex="0"
    :aria-label="`${title}. ${status}`"
    :aria-grabbed="isDragging"
    class="workflow-canvas-node"
    :class="[`is-${node.type}`, `status-${status}`, { 'is-selected': selected }]"
    :style="{ left: `${node.position.x}px`, top: `${node.position.y}px` }"
    @click="$emit('select-node', node.id)"
    @keydown.enter.prevent="$emit('select-node', node.id)"
    @keydown.space.prevent="$emit('select-node', node.id)"
    @keydown="handleKeydown"
    @pointerdown="handlePointerDown"
  >
    <button
      v-if="deletable"
      type="button"
      class="node-delete-button"
      aria-label="Delete node"
      @click.stop="$emit('delete-node', node.id)"
      @pointerdown.stop
    >
      ×
    </button>
    <span class="node-kind">{{ node.type }}</span>
    <span class="node-title">{{ title }}</span>
    <span v-if="subtitle" class="node-subtitle">{{ subtitle }}</span>
    <WorkflowNodeStatusBadge :status="status" />
  </div>
</template>

<script setup lang="ts">
  import { ref } from 'vue'
  import type { WorkflowStepStatus } from '@/workflow/artifact-types'
  import type { WorkflowCanvasNode } from '@/workflow/template-types'
  import WorkflowNodeStatusBadge from './WorkflowNodeStatusBadge.vue'

  const props = defineProps<{
    node: WorkflowCanvasNode
    title: string
    subtitle?: string
    status: WorkflowStepStatus
    selected?: boolean
    deletable?: boolean
  }>()

  const emit = defineEmits<{
    (event: 'select-node', nodeId: string): void
    (event: 'delete-node', nodeId: string): void
    (event: 'move-node', payload: { nodeId: string; position: { x: number; y: number } }): void
  }>()

  const isDragging = ref(false)

  function handleKeydown(event: KeyboardEvent) {
    const offsetByKey: Record<string, { x: number; y: number }> = {
      ArrowUp: { x: 0, y: -16 },
      ArrowDown: { x: 0, y: 16 },
      ArrowLeft: { x: -16, y: 0 },
      ArrowRight: { x: 16, y: 0 }
    }
    const offset = offsetByKey[event.key]
    if (!offset) return
    event.preventDefault()
    emit('move-node', {
      nodeId: props.node.id,
      position: { x: props.node.position.x + offset.x, y: props.node.position.y + offset.y }
    })
  }

  function handlePointerDown(event: PointerEvent) {
    if (event.button !== 0) {
      return
    }

    const startX = event.clientX
    const startY = event.clientY
    const startPosition = props.node.position
    let hasDragged = false
    isDragging.value = true

    const handlePointerMove = (moveEvent: PointerEvent) => {
      const deltaX = moveEvent.clientX - startX
      const deltaY = moveEvent.clientY - startY
      if (Math.abs(deltaX) > 2 || Math.abs(deltaY) > 2) {
        hasDragged = true
      }

      emit('move-node', {
        nodeId: props.node.id,
        position: {
          x: startPosition.x + deltaX,
          y: startPosition.y + deltaY
        }
      })
    }

    const handlePointerUp = () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
      isDragging.value = false
      if (hasDragged) {
        event.preventDefault()
      }
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp, { once: true })
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-canvas-node {
    position: absolute;
    width: 188px;
    min-height: 112px;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 7px;
    padding: @spacing-md;
    border: 1px solid @accent-color-border;
    border-radius: @border-radius-md;
    background: @bg-elevated;
    box-shadow: @shadow-md;
    color: @text-color-light-primary;
    text-align: left;
    cursor: grab;
    user-select: none;
    touch-action: none;
    transition:
      transform @transition-fast,
      border-color @transition-fast,
      box-shadow @transition-fast;
  }

  .workflow-canvas-node:hover,
  .workflow-canvas-node:focus-visible {
    transform: translateY(-2px);
    border-color: rgba(59, 130, 246, 0.35);
    box-shadow: @shadow-lg;
    outline: none;
  }

  .workflow-canvas-node:active {
    cursor: grabbing;
  }

  .node-delete-button {
    position: absolute;
    top: 8px;
    right: 8px;
    width: 24px;
    height: 24px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid rgba(255, 77, 79, 0.26);
    border-radius: 50%;
    background: @bg-surface;
    color: @error-color;
    font-size: 16px;
    font-weight: 800;
    line-height: 1;
    cursor: pointer;
  }

  .node-delete-button:hover,
  .node-delete-button:focus-visible {
    background: @error-color;
    color: #fff;
    outline: none;
  }

  .workflow-canvas-node.is-selected {
    border-color: @accent-color;
    box-shadow: 0 0 0 3px @accent-color-light, @shadow-lg;
  }

  .node-kind {
    color: @text-color-light-tertiary;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0;
    text-transform: uppercase;
  }

  .node-title {
    width: 100%;
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    font-weight: 800;
    line-height: 1.25;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .node-subtitle {
    width: 100%;
    min-height: 30px;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .is-input {
    border-left: 4px solid @info-color;
  }

  .is-tool {
    border-left: 4px solid @accent-color;
  }

  .is-result {
    border-left: 4px solid @success-color;
  }

  .status-failed {
    border-left-color: @error-color;
  }
</style>
